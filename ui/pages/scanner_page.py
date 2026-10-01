import office_profile
import os
import html
import datetime
import time
from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton, QTabWidget, QFrame, QFileDialog, QMessageBox, QProgressBar, QListWidget, QListWidgetItem, QGridLayout, QScrollArea, QMenu, QRadioButton, QButtonGroup, QDateEdit, QDialog, QCheckBox
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QStandardItemModel, QStandardItem, QCursor

# Import business logic
import auth
import reception
import ocr_engine
import contract_templates
import notary_checker
import pdf_generator
import config
from ui.components.audio_recorder import AudioRecorder


# The collapsible section moved to ui/components/collapsible_box.py when the
# Paramètres page needed the same behaviour. Imported rather than duplicated.
from ui.components.collapsible_box import CollapsibleSection


# ── Unified Asynchronous Pipeline Thread ──
# Duree maximale d'attente d'un pre-scan de CIN deja lance, en secondes.
# Auparavant l'attente etait un join() sans limite : quand le scan n'aboutissait
# pas (reseau coupe, cles refusees), la generation restait bloquee indefiniment,
# barre de progression tournante et aucun message. Passe ce delai on continue
# sans la carte, et le notaire saisit les champs a la main.
# 95 s = les 80 s du pire cas d'une cle (2 modeles x 40 s) plus une marge.
OCR_JOIN_TIMEOUT_S = 95


class UnifiedPipelineThread(QThread):
    finished = Signal(dict)
    
    def __init__(self, contract_type, p1_data, p2_data, procuration_text, audio_bytes, audio_mime, voice_text, api_key, provider, model, contract_vars, include_audio_party_info=False):
        super().__init__()
        self.contract_type = contract_type
        self.p1_data = p1_data
        self.p2_data = p2_data
        self.procuration_text = procuration_text
        self.audio_bytes = audio_bytes
        self.audio_mime = audio_mime
        self.voice_text = voice_text
        self.api_key = api_key
        self.provider = provider
        self.model = model
        self.contract_vars = contract_vars.copy()
        self.include_audio_party_info = include_audio_party_info
        
    def run(self):
        import time, sys
        t_global_start = time.perf_counter()
        sys.stdout.write(f"\n[TIMING 0.00s] === 🚀 STARTING PIPELINE GENERATION ===\n")
        sys.stdout.flush()

        results = {
            "success": True,
            "fatal": False,
            "error": "",
            "logs": [],
            "warnings": [],
            "cards_attempted": 0,
            "cards_read": 0,
            "audio_attempted": False,
            "audio_ok": False,
            "party1_list": [],
            "party2_list": [],
            "extracted_vars": {},
            "extra_foussoul": [],
            "spoken_content": ""
        }

        try:
            import concurrent.futures
            from cin_extractor import extract_cin_dual_faces
            from voice_verifier import (
                transcribe_audio_bytes,
                extract_variables_from_spoken_text,
                normalise_foussoul,
            )

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                # 1. Dispatch Party 1 CIN OCR tasks in parallel
                p1_tasks = []
                for idx, p1 in enumerate(self.p1_data):
                    if p1.get("extracted") and p1["extracted"].get("full_name"):
                        t_curr = time.perf_counter() - t_global_start
                        sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 1 Card {idx+1}: Pre-scanned cache HIT! Name={p1['extracted'].get('full_name')} (0.0s delay)\n")
                        sys.stdout.flush()
                    elif p1.get("ocr_thread") and p1["ocr_thread"].is_alive():
                        t_wait_start = time.perf_counter()
                        t_curr = time.perf_counter() - t_global_start
                        sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 1 Card {idx+1}: Background pre-scan active - joining active thread...\n")
                        sys.stdout.flush()
                        p1["ocr_thread"].join(timeout=OCR_JOIN_TIMEOUT_S)
                        if p1.get("party_dict") and p1["party_dict"].get("extracted"):
                            p1["extracted"] = p1["party_dict"]["extracted"]
                        if p1["ocr_thread"].is_alive():
                            # Le fil tourne encore : on l'abandonne plutot que
                            # de bloquer la generation entiere sur une carte.
                            results["warnings"].append(
                                f"بطاقة الطرف الأول {idx+1}: تعذّرت قراءتها خلال {OCR_JOIN_TIMEOUT_S} ثانية — يُرجى إدخال البيانات يدويًا.")
                            try:
                                from system_guardian import log_system_error
                                log_system_error(
                                    f"pre-scan CIN abandonne apres {OCR_JOIN_TIMEOUT_S}s (p1 carte {idx+1})",
                                    TimeoutError("le fil de pre-scan ne rendait pas la main"))
                            except Exception:
                                pass

                        t_wait_dur = time.perf_counter() - t_wait_start
                        t_curr = time.perf_counter() - t_global_start
                        if p1.get("extracted") and p1["extracted"].get("full_name"):
                            sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 1 Card {idx+1}: Joined background pre-scan in {t_wait_dur:.2f}s! Name={p1['extracted'].get('full_name')}\n")
                        sys.stdout.flush()
                    elif p1.get("client_id"):
                        t_curr = time.perf_counter() - t_global_start
                        sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 1 Card {idx+1}: Registered Client database HIT! (0.0s delay)\n")
                        sys.stdout.flush()
                    elif p1.get("front_bytes"):
                        t_curr = time.perf_counter() - t_global_start
                        sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 1 Card {idx+1}: Cache MISS - Dispatching Vision OCR in parallel thread...\n")
                        sys.stdout.flush()
                        results["cards_attempted"] += 1
                        fut = executor.submit(extract_cin_dual_faces, p1["front_bytes"], p1.get("back_bytes"), self.api_key, self.model, self.provider)
                        p1_tasks.append((idx, fut))

                # 2. Dispatch Party 2 CIN OCR tasks in parallel
                p2_tasks = []
                for idx, p2 in enumerate(self.p2_data):
                    if p2.get("extracted") and p2["extracted"].get("full_name"):
                        t_curr = time.perf_counter() - t_global_start
                        sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 2 Card {idx+1}: Pre-scanned cache HIT! Name={p2['extracted'].get('full_name')} (0.0s delay)\n")
                        sys.stdout.flush()
                    elif p2.get("ocr_thread") and p2["ocr_thread"].is_alive():
                        t_wait_start = time.perf_counter()
                        t_curr = time.perf_counter() - t_global_start
                        sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 2 Card {idx+1}: Background pre-scan active - joining active thread...\n")
                        sys.stdout.flush()
                        p2["ocr_thread"].join(timeout=OCR_JOIN_TIMEOUT_S)
                        if p2.get("party_dict") and p2["party_dict"].get("extracted"):
                            p2["extracted"] = p2["party_dict"]["extracted"]
                        if p2["ocr_thread"].is_alive():
                            # Le fil tourne encore : on l'abandonne plutot que
                            # de bloquer la generation entiere sur une carte.
                            results["warnings"].append(
                                f"بطاقة الطرف الثاني {idx+1}: تعذّرت قراءتها خلال {OCR_JOIN_TIMEOUT_S} ثانية — يُرجى إدخال البيانات يدويًا.")
                            try:
                                from system_guardian import log_system_error
                                log_system_error(
                                    f"pre-scan CIN abandonne apres {OCR_JOIN_TIMEOUT_S}s (p2 carte {idx+1})",
                                    TimeoutError("le fil de pre-scan ne rendait pas la main"))
                            except Exception:
                                pass

                        t_wait_dur = time.perf_counter() - t_wait_start
                        t_curr = time.perf_counter() - t_global_start
                        if p2.get("extracted") and p2["extracted"].get("full_name"):
                            sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 2 Card {idx+1}: Joined background pre-scan in {t_wait_dur:.2f}s! Name={p2['extracted'].get('full_name')}\n")
                        sys.stdout.flush()
                    elif p2.get("client_id"):
                        t_curr = time.perf_counter() - t_global_start
                        sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 2 Card {idx+1}: Registered Client database HIT! (0.0s delay)\n")
                        sys.stdout.flush()
                    elif p2.get("front_bytes"):
                        t_curr = time.perf_counter() - t_global_start
                        sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 2 Card {idx+1}: Cache MISS - Dispatching Vision OCR in parallel thread...\n")
                        sys.stdout.flush()
                        results["cards_attempted"] += 1
                        fut = executor.submit(extract_cin_dual_faces, p2["front_bytes"], p2.get("back_bytes"), self.api_key, self.model, self.provider)
                        p2_tasks.append((idx, fut))

                # 3. Dispatch Audio Transcription task concurrently with CIN OCR
                audio_fut = None
                spoken_content = self.voice_text.strip()
                if self.audio_bytes:
                    t_curr = time.perf_counter() - t_global_start
                    sys.stdout.write(f"[TIMING {t_curr:.2f}s] Audio Audio Bytes Present ({len(self.audio_bytes)} bytes) - Dispatching Transcription in parallel...\n")
                    sys.stdout.flush()
                    results["audio_attempted"] = True
                    results["logs"].append("3/3 تفريغ التسجيل الصوتي بالذكاء الاصطناعي...")
                    audio_fut = executor.submit(
                        transcribe_audio_bytes,
                        audio_bytes=self.audio_bytes,
                        api_key=self.api_key,
                        mime_type=self.audio_mime,
                        model_name=self.model,
                        provider=self.provider
                    )

                # 4. Wait for audio transcription to finish if active
                if audio_fut:
                    t_aud_start = time.perf_counter()
                    res_aud = audio_fut.result()
                    t_aud_dur = time.perf_counter() - t_aud_start
                    t_curr = time.perf_counter() - t_global_start
                    sys.stdout.write(f"[TIMING {t_curr:.2f}s] Audio Transcription finished in {t_aud_dur:.2f}s!\n")
                    sys.stdout.flush()
                    if res_aud.get("success"):
                        spoken_content = res_aud.get("transcription", spoken_content)
                        results["audio_ok"] = True
                        results["logs"].append("تم تفريغ التسجيل الصوتي بنجاح.")
                    else:
                        err_msg = res_aud.get("error", "فشل التفريغ الصوتي")
                        results["logs"].append(f" تنبيه صوتي: {err_msg}")
                        results["warnings"].append(f"التفريغ الصوتي: {err_msg}")
                        results["success"] = False

                results["spoken_content"] = spoken_content

                # 5. Extract variables and clauses in 1 fast unified pass
                if spoken_content.strip():
                    t_var_start = time.perf_counter()
                    t_curr = time.perf_counter() - t_global_start
                    sys.stdout.write(f"[TIMING {t_curr:.2f}s] Extracting variables & clauses from dictation text...\n")
                    sys.stdout.flush()
                    try:
                        spk_vars = extract_variables_from_spoken_text(spoken_content, self.api_key, self.model, self.provider)
                        t_var_dur = time.perf_counter() - t_var_start
                        t_curr = time.perf_counter() - t_global_start
                        sys.stdout.write(f"[TIMING {t_curr:.2f}s] Spoken variable extraction finished in {t_var_dur:.2f}s!\n")
                        sys.stdout.flush()
                        if spk_vars:
                            results["extracted_vars"] = spk_vars
                            if "foussoul" in spk_vars and isinstance(spk_vars["foussoul"], list) and spk_vars["foussoul"]:
                                results["extra_foussoul"] = normalise_foussoul(spk_vars["foussoul"])
                    except Exception as ex_vars:
                        results["logs"].append(f" تعذّر استخراج المتغيرات من النص المنطوق: {ex_vars}")
                        results["warnings"].append(f"استخراج المتغيرات من الإملاء: {ex_vars}")
                        results["success"] = False

                # 6. Gather Party 1 CIN Results
                for idx, p1 in enumerate(self.p1_data):
                    extracted = {}
                    if p1.get("extracted") and p1["extracted"].get("full_name"):
                        extracted = p1["extracted"]
                        results["cards_read"] += 1
                        results["logs"].append(f" تم استخدام معطيات البطاقة المستخرجة (الطرف الأول {idx+1}): {extracted.get('full_name')}")
                    elif p1.get("client_id"):
                        sc = reception.get_client_by_id(p1["client_id"])
                        if sc:
                            extracted = {
                                "full_name": sc.get("full_name", ""),
                                "prenom": sc.get("prenom", ""),
                                "nom": sc.get("nom", ""),
                                "father_name": sc.get("father_name", ""),
                                "grandfather_name": sc.get("grandfather_name", ""),
                                "cin_number": sc.get("cin_number", ""),
                                "issue_date": sc.get("cin_issue_date") or sc.get("cin_date_place", ""),
                                "cin_issue_date": sc.get("cin_issue_date", ""),
                                "cin_issue_place": sc.get("cin_issue_place", ""),
                                "job": sc.get("profession", ""),
                                "address": sc.get("address", ""),
                                "birth_date": sc.get("birth_date", ""),
                                "birth_place": sc.get("birth_place", ""),
                                "marital_status": sc.get("marital_status", "")
                            }
                            results["logs"].append(f" تم تحميل الحريف المسجل (الطرف الأول {idx+1}): {extracted.get('full_name')}")
                    else:
                        for task_idx, fut in p1_tasks:
                            if task_idx == idx:
                                t_ocr_start = time.perf_counter()
                                res_p1 = fut.result()
                                t_ocr_dur = time.perf_counter() - t_ocr_start
                                t_curr = time.perf_counter() - t_global_start
                                sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 1 Vision OCR result collected in {t_ocr_dur:.2f}s!\n")
                                sys.stdout.flush()
                                if res_p1.get("success") and res_p1.get("data", {}).get("full_name"):
                                    extracted = res_p1["data"]
                                    results["cards_read"] += 1
                                    results["logs"].append(f" تم استخراج معطيات بطاقة البائع {idx+1}: {extracted.get('full_name')}")
                                else:
                                    err = res_p1.get("error") or "فشل قراءة بطاقة التعريف"
                                    results["logs"].append(f" تنبيه بطاقة البائع {idx+1}: {err}")
                                    results["warnings"].append(f"بطاقة الطرف الأول {idx+1}: {err}")
                                    results["success"] = False
                    # Merge missing fields (e.g. dictated Job or Address) from audio dictation only if toggle is ON
                    if results.get("extracted_vars") and self.include_audio_party_info:
                        sv = results["extracted_vars"]
                        if not extracted.get("full_name"):
                            extracted["full_name"] = sv.get("party1_name") or sv.get("party_1_name") or ""
                        if not extracted.get("birth_place"):
                            extracted["birth_place"] = sv.get("party1_birthplace") or ""
                        if not extracted.get("birth_date"):
                            extracted["birth_date"] = sv.get("party1_birthdate") or ""
                        if not extracted.get("job"):
                            extracted["job"] = sv.get("party1_job") or ""
                        if not extracted.get("cin_number"):
                            extracted["cin_number"] = sv.get("party1_cin") or ""
                        if not extracted.get("issue_date"):
                            extracted["issue_date"] = sv.get("party1_cin_date") or ""
                        if not extracted.get("address"):
                            extracted["address"] = sv.get("party1_address") or ""

                    results["party1_list"].append(extracted)

                # 7. Gather Party 2 CIN Results
                for idx, p2 in enumerate(self.p2_data):
                    extracted = {}
                    if p2.get("extracted") and p2["extracted"].get("full_name"):
                        extracted = p2["extracted"]
                        results["cards_read"] += 1
                        results["logs"].append(f" تم استخدام معطيات البطاقة المستخرجة (الطرف الثاني {idx+1}): {extracted.get('full_name')}")
                    elif p2.get("client_id"):
                        sc = reception.get_client_by_id(p2["client_id"])
                        if sc:
                            extracted = {
                                "full_name": sc.get("full_name", ""),
                                "prenom": sc.get("prenom", ""),
                                "nom": sc.get("nom", ""),
                                "father_name": sc.get("father_name", ""),
                                "grandfather_name": sc.get("grandfather_name", ""),
                                "cin_number": sc.get("cin_number", ""),
                                "issue_date": sc.get("cin_issue_date") or sc.get("cin_date_place", ""),
                                "cin_issue_date": sc.get("cin_issue_date", ""),
                                "cin_issue_place": sc.get("cin_issue_place", ""),
                                "job": sc.get("profession", ""),
                                "address": sc.get("address", ""),
                                "birth_date": sc.get("birth_date", ""),
                                "birth_place": sc.get("birth_place", ""),
                                "marital_status": sc.get("marital_status", "")
                            }
                            results["logs"].append(f" تم تحميل الحريف المسجل (الطرف الثاني {idx+1}): {extracted.get('full_name')}")
                    else:
                        for task_idx, fut in p2_tasks:
                            if task_idx == idx:
                                t_ocr_start = time.perf_counter()
                                res_p2 = fut.result()
                                t_ocr_dur = time.perf_counter() - t_ocr_start
                                t_curr = time.perf_counter() - t_global_start
                                sys.stdout.write(f"[TIMING {t_curr:.2f}s] Party 2 Vision OCR result collected in {t_ocr_dur:.2f}s!\n")
                                sys.stdout.flush()
                                if res_p2.get("success") and res_p2.get("data", {}).get("full_name"):
                                    extracted = res_p2["data"]
                                    results["cards_read"] += 1
                                    results["logs"].append(f" تم استخراج معطيات بطاقة المشتري {idx+1}: {extracted.get('full_name')}")
                                else:
                                    err = res_p2.get("error") or "فشل قراءة بطاقة التعريف"
                                    results["logs"].append(f" تنبيه بطاقة المشتري {idx+1}: {err}")
                                    results["warnings"].append(f"بطاقة الطرف الثاني {idx+1}: {err}")
                                    results["success"] = False

                    # Merge missing fields (e.g. dictated Job or Address) from audio dictation only if toggle is ON
                    if results.get("extracted_vars") and self.include_audio_party_info:
                        sv = results["extracted_vars"]
                        if not extracted.get("full_name"):
                            extracted["full_name"] = sv.get("party2_name") or sv.get("party_2_name") or ""
                        if not extracted.get("birth_place"):
                            extracted["birth_place"] = sv.get("party2_birthplace") or ""
                        if not extracted.get("birth_date"):
                            extracted["birth_date"] = sv.get("party2_birthdate") or ""
                        if not extracted.get("job"):
                            extracted["job"] = sv.get("party2_job") or ""
                        if not extracted.get("cin_number"):
                            extracted["cin_number"] = sv.get("party2_cin") or ""
                        if not extracted.get("issue_date"):
                            extracted["issue_date"] = sv.get("party2_cin_date") or ""
                        if not extracted.get("address"):
                            extracted["address"] = sv.get("party2_address") or ""

                    results["party2_list"].append(extracted)

        except Exception as e:
            results["success"] = False
            results["fatal"] = True
            results["error"] = str(e)

        t_total = time.perf_counter() - t_global_start
        sys.stdout.write(f"[TIMING {t_total:.2f}s] === 🏁 TOTAL PIPELINE EXECUTION TIME: {t_total:.2f} SECONDS ===\n\n")
        sys.stdout.flush()

        self.finished.emit(results)


class ScannerSettingsDialog(QDialog):
    """
    Sleek, modern, ultra-minimalist modal dialog for Scanner Page contract settings.
    Contains:
    1. Contract Date selection (Automatic vs Custom Date)
    2. Audio Dictation Identity Extraction toggle
    """
    def __init__(self, parent_scanner_page):
        super().__init__(parent_scanner_page)
        self.scanner = parent_scanner_page
        self.lang = self.scanner.lang
        self.setWindowTitle("⚙️ إعدادات العقد" if self.lang == "ar" else "⚙️ Paramètres")
        self.setFixedWidth(410)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
        """)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # Header Title
        lbl_title = QLabel("⚙️ إعدادات العقد والرقمنة" if self.lang == "ar" else "⚙️ Configuration du contrat")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a;")
        layout.addWidget(lbl_title)

        # ── 1. Contract Date Card ──
        date_card = QFrame(self)
        date_card.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        date_lay = QVBoxLayout(date_card)
        date_lay.setSpacing(8)

        lbl_date = QLabel("📅 تاريخ تحرير العقد" if self.lang == "ar" else "📅 Date du contrat")
        lbl_date.setStyleSheet("font-size: 12px; font-weight: bold; color: #334155; border: none;")
        date_lay.addWidget(lbl_date)

        radio_lay = QHBoxLayout()
        self.radio_auto = QRadioButton("تلقائي (اليوم)" if self.lang == "ar" else "Aujourd'hui", date_card)
        self.radio_custom = QRadioButton("تاريخ مخصص" if self.lang == "ar" else "Date spécifique", date_card)
        self.radio_auto.setStyleSheet("font-size: 12px; font-weight: 600; color: #1e293b;")
        self.radio_custom.setStyleSheet("font-size: 12px; font-weight: 600; color: #1e293b;")

        is_auto = self.scanner.radio_date_auto.isChecked()
        self.radio_auto.setChecked(is_auto)
        self.radio_custom.setChecked(not is_auto)

        radio_lay.addWidget(self.radio_auto)
        radio_lay.addWidget(self.radio_custom)
        date_lay.addLayout(radio_lay)

        from PySide6.QtCore import QDate
        from ui.components.calendar_utils import configure_calendar

        self.date_edit = QDateEdit(self.scanner.custom_date_edit.date(), date_card)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy/MM/dd")
        self.date_edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.date_edit.setFixedHeight(32)
        self.date_edit.setEnabled(not is_auto)
        self.date_edit.setStyleSheet("""
            QDateEdit {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QDateEdit:disabled {
                background-color: #f1f5f9;
                color: #94a3b8;
            }
        """)
        configure_calendar(self.date_edit)

        self.radio_auto.toggled.connect(lambda checked: self.date_edit.setEnabled(not checked))
        date_lay.addWidget(self.date_edit)

        layout.addWidget(date_card)

        # ── 2. Audio Identity Extraction Card ──
        audio_card = QFrame(self)
        audio_card.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        audio_lay = QVBoxLayout(audio_card)
        audio_lay.setSpacing(8)

        lbl_audio = QLabel("🎙️ استخراج معطيات الأطراف من الصوت" if self.lang == "ar" else "🎙️ Identité des parties via vocal")
        lbl_audio.setStyleSheet("font-size: 12px; font-weight: bold; color: #334155; border: none;")
        audio_lay.addWidget(lbl_audio)

        self.btn_audio_party_toggle = QPushButton(audio_card)
        self.btn_audio_party_toggle.setFixedHeight(36)
        self.btn_audio_party_toggle.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_audio_party_toggle.setCheckable(True)
        self.btn_audio_party_toggle.setChecked(self.scanner.btn_audio_party_toggle.isChecked())
        self.btn_audio_party_toggle.clicked.connect(self._update_audio_toggle_ui)
        self._update_audio_toggle_ui()
        audio_lay.addWidget(self.btn_audio_party_toggle)

        layout.addWidget(audio_card)

        # Actions (Single clean Apply Button)
        btn_apply = QPushButton("تطبيق الإعدادات" if self.lang == "ar" else "Appliquer", self)
        btn_apply.setFixedHeight(38)
        btn_apply.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #1e40af;
                color: #ffffff;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1e3a8a;
            }
        """)
        btn_apply.clicked.connect(self.save_and_accept)
        layout.addWidget(btn_apply)

    def _update_audio_toggle_ui(self):
        is_on = self.btn_audio_party_toggle.isChecked()
        if is_on:
            text = "🎙️ مفعّل (تضمين هويات الأطراف)" if self.lang == "ar" else "🎙️ Activé (Inclure identités)"
            style = """
                QPushButton {
                    background-color: #ecfdf5;
                    color: #047857;
                    border: 1px solid #10b981;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: bold;
                }
            """
        else:
            text = "🔇 معطّل (فقط الفصول والملكية)" if self.lang == "ar" else "🔇 Désactivé (Clauses & bien uniquement)"
            style = """
                QPushButton {
                    background-color: #ffffff;
                    color: #475569;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: bold;
                }
            """
        self.btn_audio_party_toggle.setText(text)
        self.btn_audio_party_toggle.setStyleSheet(style)

    def save_and_accept(self):
        if self.radio_auto.isChecked():
            self.scanner.radio_date_auto.setChecked(True)
        else:
            self.scanner.radio_date_custom.setChecked(True)
            self.scanner.custom_date_edit.setDate(self.date_edit.date())

        self.scanner.btn_audio_party_toggle.setChecked(self.btn_audio_party_toggle.isChecked())
        self.scanner.update_audio_party_toggle_ui()

        self.accept()


class ScannerPage(QWidget):
    client_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang = auth.session_state.lang
        
        # Audio Recorder component
        self.audio_recorder = AudioRecorder()
        self.audio_recorder.recording_started.connect(self.on_recording_started)
        self.audio_recorder.recording_stopped.connect(self.on_recording_stopped)
        self.audio_recorder.error_occurred.connect(self.on_recording_error)
        
        self.recorded_file_path = ""
        self.audio_bytes = None
        self.audio_mime = "audio/wav"

        self.rec_timer = QTimer(self)
        self.rec_timer.timeout.connect(self._update_rec_timer_display)
        self.rec_seconds = 0

        # State Variables
        # Configured on the Settings page; re-read before each generation
        # (see reload_ai_engine).
        self.ocr_provider, self.ocr_model = config.load_ai_engine()
        self.ocr_api_key = config.load_saved_api_keys(self.ocr_provider)

        self.selected_contract_type = "عقد بيع"
        self.contract_vars = contract_templates.get_default_variables("عقد بيع")
        self.ocr_edited_text = ""

        # Full extracted party records and AI clauses from the last successful run.
        # The contract preview is rebuilt from THESE, never from a reduced copy, so a
        # later refresh cannot silently drop CIN issue dates, birth data or clauses.
        self.p1_extracted = []
        self.p2_extracted = []
        self.extra_foussoul = []
        self.audit_result = None

        # Multi-party dynamic state lists
        self.p1_parties = [{"client_id": "", "front_bytes": None, "back_bytes": None, "front_lbl": "لا يوجد", "back_lbl": "لا يوجد"}]
        self.p2_parties = [{"client_id": "", "front_bytes": None, "back_bytes": None, "front_lbl": "لا يوجد", "back_lbl": "لا يوجد"}]
        
        self.clients_list = []

        # Audio recording state
        self.recorded_file_path = ""
        self.audio_bytes = None
        self.audio_mime = "audio/wav"
        self.rec_seconds = 0
        self.audio_recorder = AudioRecorder()
        self.audio_recorder.recording_started.connect(self.on_recording_started)
        self.audio_recorder.recording_stopped.connect(self.on_recording_stopped)
        self.audio_recorder.error_occurred.connect(self.on_recording_error)

        self.rec_timer = QTimer(self)
        self.rec_timer.timeout.connect(self._update_rec_timer_display)

        # Audio party toggle state managed via ScannerSettingsDialog
        self.btn_audio_party_toggle = QPushButton()
        self.btn_audio_party_toggle.setCheckable(True)
        self.btn_audio_party_toggle.setChecked(False)
        self.btn_audio_party_toggle.hide()

        self.init_ui()
        self.load_clients_list()
        self.populate_contract_types()
        self.on_contract_type_changed()

    def init_ui(self):
        # Main Layout using Master ScrollArea
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        master_scroll = QScrollArea(self)
        master_scroll.setWidgetResizable(True)
        master_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        master_panel = QFrame()
        master_panel.setFrameShape(QFrame.Shape.NoFrame)
        master_lay = QVBoxLayout(master_panel)
        master_lay.setContentsMargins(15, 15, 15, 30)
        master_lay.setSpacing(30)

        # ── 1. LEFT PANEL : CONFIGURATION & DYNAMIC INPUTS (WITH SCROLL) ──────
        left_panel = QFrame(master_panel)
        left_panel.setFrameShape(QFrame.Shape.NoFrame)
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(15)
        master_lay.addWidget(left_panel)

        # Title


        # Single Unified Selectors Box
        selectors_box = QHBoxLayout()
        selectors_box.setSpacing(10)

        self.lbl_type = QLabel("Type de contrat :" if self.lang == "fr" else "نوع العقد :", left_panel)
        self.lbl_type.setStyleSheet("font-size:13px; font-weight:700; color:#1e293b; border:none;")

        self.type_btn = QPushButton(left_panel)
        self.type_btn.setFixedHeight(36)
        self.type_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.type_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: bold;
                text-align: right;
            }
            QPushButton:hover {
                background-color: #f8fafc;
                border-color: #3b82f6;
            }
        """)

        self.btn_farida = QPushButton("🧮 حاسبة الفريضة" if self.lang == "ar" else "🧮 Calculateur d'Héritage", left_panel)
        self.btn_farida.setFixedHeight(36)
        self.btn_farida.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_farida.setStyleSheet("""
            QPushButton {
                background-color: #1e40af;
                color: #ffffff;
                border-radius: 6px;
                padding: 0 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1e3a8a;
            }
        """)
        self.btn_farida.clicked.connect(self.open_farida_calculator)

        self.btn_scanner_settings = QPushButton("⚙️ خيارات العقد" if self.lang == "ar" else "⚙️ Options du contrat", left_panel)
        self.btn_scanner_settings.setFixedHeight(36)
        self.btn_scanner_settings.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_scanner_settings.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc;
                color: #1e3a8a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #eff6ff;
                border-color: #3b82f6;
            }
        """)
        self.btn_scanner_settings.clicked.connect(self.open_scanner_settings_dialog)

        selectors_box.addWidget(self.lbl_type)
        selectors_box.addWidget(self.type_btn, 2)
        selectors_box.addWidget(self.btn_farida)
        selectors_box.addWidget(self.btn_scanner_settings)
        left_lay.addLayout(selectors_box)

        # Single Unified Dossier Selector Box & Custom Dossier Number Input
        dossier_box = QHBoxLayout()
        self.lbl_dossier = QLabel("الملف التوثيقي المربوط :" if self.lang == "ar" else "Dossier associé :", left_panel)
        self.lbl_dossier.setStyleSheet("font-size:13px; font-weight:700; color:#1e3a8a; border:none;")
        self.dossier_combo = QComboBox(left_panel)
        self.dossier_combo.setFixedHeight(36)
        self.dossier_combo.setStyleSheet("""
            QComboBox {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QComboBox:hover {
                border-color: #3b82f6;
            }
        """)
        self.dossier_combo.addItem("-- إنشاء ملف جديد لهذا العقد --" if self.lang == "ar" else "-- Nouveau dossier --", "")
        self.dossier_combo.currentIndexChanged.connect(self.on_dossier_combo_changed)

        self.lbl_dossier_num = QLabel("رقم الملف :" if self.lang == "ar" else "N° Dossier :", left_panel)
        self.lbl_dossier_num.setStyleSheet("font-size:13px; font-weight:700; color:#1e3a8a; border:none;")
        
        self.var_dossier_num = QLineEdit(left_panel)
        self.var_dossier_num.setFixedHeight(36)
        self.var_dossier_num.setPlaceholderText("رقم الملف (مثال: 105)" if self.lang == "ar" else "N° dossier (ex: 105)")
        self.var_dossier_num.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
            QLineEdit:disabled {
                background-color: #f1f5f9;
                color: #64748b;
            }
        """)

        dossier_box.addWidget(self.lbl_dossier)
        dossier_box.addWidget(self.dossier_combo, 2)
        dossier_box.addWidget(self.lbl_dossier_num)
        dossier_box.addWidget(self.var_dossier_num, 1)
        left_lay.addLayout(dossier_box)

        # ── Internal Contract Date State ──
        from PySide6.QtCore import QDate
        from ui.components.calendar_utils import configure_calendar
        
        self.radio_date_auto = QRadioButton()
        self.radio_date_auto.setChecked(True)
        self.radio_date_auto.hide()

        self.radio_date_custom = QRadioButton()
        self.radio_date_custom.hide()

        self.custom_date_edit = QDateEdit(QDate.currentDate())
        self.custom_date_edit.setCalendarPopup(True)
        self.custom_date_edit.setDisplayFormat("yyyy/MM/dd")
        self.custom_date_edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        configure_calendar(self.custom_date_edit)
        self.custom_date_edit.hide()
        
        self.lbl_date_preview = QLabel()
        self.lbl_date_preview.hide()

        self.radio_date_auto.toggled.connect(self.on_date_mode_changed)
        self.radio_date_custom.toggled.connect(self.on_date_mode_changed)
        self.custom_date_edit.dateChanged.connect(self.on_custom_date_changed)

        # ── Collapsible Section 1: CIN Cards & Registered Clients ──
        self.sec_cin = CollapsibleSection(("1. Cartes d'identité et clients enregistrés" if self.lang == "fr" else "1. بطاقات التعريف الوطنية والحرفاء المسجلين"), expanded=False, parent=left_panel)
        self.parties_lay = QHBoxLayout()
        
        self.col_p1_container = QWidget()
        self.col_p1_lay = QVBoxLayout(self.col_p1_container)
        self.col_p1_lay.setSpacing(8)
        self.col_p1_lay.setContentsMargins(0, 0, 0, 0)
        
        self.col_p2_container = QWidget()
        self.col_p2_lay = QVBoxLayout(self.col_p2_container)
        self.col_p2_lay.setSpacing(8)
        self.col_p2_lay.setContentsMargins(0, 0, 0, 0)
        
        self.parties_lay.addWidget(self.col_p1_container, 1)
        self.parties_lay.addWidget(self.col_p2_container, 1)
        self.sec_cin.add_layout(self.parties_lay)
        
        # Procuration/Representation input
        self.sec_cin.add_widget(QLabel(("Procuration ou représentation (optionnel) :" if self.lang == "fr" else "بيانات التوكيل (اختياري) :")))
        self.procuration_input = QTextEdit(self.sec_cin)
        self.procuration_input.setMaximumHeight(50)
        self.sec_cin.add_widget(self.procuration_input)
        left_lay.addWidget(self.sec_cin)

        # ── Collapsible Section 2: Audio & Live Dictation Box (الإملاء والكتابة المباشرة) ──
        self.sec_audio = CollapsibleSection(
            ("2. Dictée et transcription orale (Optionnel)" if self.lang == "fr" else "2. الإملاء والكتابة المباشرة والتفريغ الصوتي (اختياري)"),
            expanded=False,
            parent=left_panel
        )

        self.audio_tabs = QTabWidget(self.sec_audio)
        self.audio_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #cbd5e1; border-radius: 6px; background: #ffffff; }
            QTabBar::tab { background: #f1f5f9; color: #475569; padding: 8px 14px; font-weight: bold; border-radius: 4px; margin-right: 4px; }
            QTabBar::tab:selected { background: #1e3a8a; color: #ffffff; }
        """)

        # Tab 1: Live Dictation Mic
        tab_mic = QWidget()
        mic_lay = QVBoxLayout(tab_mic)
        mic_lay.setSpacing(8)

        self.mic_status_lbl = QLabel("حالة المايكروفون : جاهز للتسجيل" if self.lang != "fr" else "Statut micro : Prêt", tab_mic)
        self.mic_status_lbl.setStyleSheet("color: #475569; font-size: 12px;")
        mic_lay.addWidget(self.mic_status_lbl)

        mic_btn_lay = QHBoxLayout()
        self.start_mic_btn = QPushButton("🎙️ بدء التسجيل" if self.lang != "fr" else "🎙️ Démarrer", tab_mic)
        self.start_mic_btn.setProperty("class", "PrimaryButton")
        self.start_mic_btn.clicked.connect(self.start_recording)

        self.stop_mic_btn = QPushButton("⏹️ إيقاف" if self.lang != "fr" else "⏹️ Arrêter", tab_mic)
        self.stop_mic_btn.setProperty("class", "SecondaryButton")
        self.stop_mic_btn.setEnabled(False)
        self.stop_mic_btn.clicked.connect(self.stop_recording)

        mic_btn_lay.addWidget(self.start_mic_btn)
        mic_btn_lay.addWidget(self.stop_mic_btn)
        mic_lay.addLayout(mic_btn_lay)

        mic_actions_lay = QHBoxLayout()
        self.save_audio_btn = QPushButton("💾 حفظ التسجيل" if self.lang != "fr" else "💾 Enregistrer", tab_mic)
        self.save_audio_btn.setProperty("class", "SecondaryButton")
        self.save_audio_btn.setVisible(False)
        self.save_audio_btn.clicked.connect(self.save_audio_to_laptop)

        self.delete_audio_btn = QPushButton("🗑️ حذف التسجيل" if self.lang != "fr" else "🗑️ Supprimer", tab_mic)
        self.delete_audio_btn.setProperty("class", "SecondaryButton")
        self.delete_audio_btn.setVisible(False)
        self.delete_audio_btn.clicked.connect(self.clear_audio_recording)

        mic_actions_lay.addWidget(self.save_audio_btn)
        mic_actions_lay.addWidget(self.delete_audio_btn)
        mic_lay.addLayout(mic_actions_lay)

        # Tab 2: Upload Audio File
        tab_file = QWidget()
        file_lay = QVBoxLayout(tab_file)
        file_lay.setSpacing(8)

        self.upload_file_btn = QPushButton("📁 اختيار ملف صوتي من الجهاز" if self.lang != "fr" else "📁 Parcourir fichier audio", tab_file)
        self.upload_file_btn.setProperty("class", "SecondaryButton")
        self.upload_file_btn.clicked.connect(self.upload_audio_file)
        file_lay.addWidget(self.upload_file_btn)

        self.audio_path_lbl = QLabel("لا يوجد ملف" if self.lang != "fr" else "Aucun fichier", tab_file)
        self.audio_path_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        file_lay.addWidget(self.audio_path_lbl)

        self.delete_file_btn = QPushButton("🗑️ حذف الملف الصوتي" if self.lang != "fr" else "🗑️ Supprimer le fichier", tab_file)
        self.delete_file_btn.setProperty("class", "SecondaryButton")
        self.delete_file_btn.setVisible(False)
        self.delete_file_btn.clicked.connect(self.clear_audio_recording)
        file_lay.addWidget(self.delete_file_btn)

        # Tab 3: Text Transcription Output
        tab_trans = QWidget()
        trans_lay = QVBoxLayout(tab_trans)
        self.transcription_output = QTextEdit(tab_trans)
        self.transcription_output.setPlaceholderText("النص المفرغ من التسجيل الصوتي سيعرض هنا..." if self.lang != "fr" else "Le texte transcrit s'affichera ici...")
        self.transcription_output.setMinimumHeight(80)
        trans_lay.addWidget(self.transcription_output)

        self.audio_tabs.addTab(tab_mic, "تسجيل مباشر" if self.lang != "fr" else "Enregistrement")
        self.audio_tabs.addTab(tab_file, "رفع ملف صوتي" if self.lang != "fr" else "Fichier audio")
        self.audio_tabs.addTab(tab_trans, "النص المفرغ" if self.lang != "fr" else "Transcription")

        self.sec_audio.add_widget(self.audio_tabs)
        left_lay.addWidget(self.sec_audio)

        # Progress bar & Actions
        self.progress_bar = QProgressBar(left_panel)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { max-height: 14px; }")
        left_lay.addWidget(self.progress_bar)

        btn_box = QHBoxLayout()
        self.generate_btn = QPushButton(("Numériser" if self.lang == "fr" else "رقمنة"), left_panel)
        self.generate_btn.setProperty("class", "PrimaryButton")
        self.generate_btn.setMinimumHeight(45)
        self.generate_btn.clicked.connect(self.run_unified_generation)
        
        self.reset_btn = QPushButton(("Retour" if self.lang == "fr" else "رجوع"), left_panel)
        self.reset_btn.setProperty("class", "SecondaryButton")
        self.reset_btn.setMinimumHeight(45)
        self.reset_btn.clicked.connect(self.reset_pipeline)
        
        btn_box.addWidget(self.generate_btn, 7)
        btn_box.addWidget(self.reset_btn, 3)
        left_lay.addLayout(btn_box)

        # ── Pipeline step report (visible in the app, not on a console) ──────────
        # The packaged build runs with --noconsole, so print() output is discarded.
        # Every step result is rendered here so the notary can see what happened.
        self.log_panel = QFrame(left_panel)
        self.log_panel.setVisible(False)
        log_panel_lay = QVBoxLayout(self.log_panel)
        log_panel_lay.setContentsMargins(0, 0, 0, 0)
        log_panel_lay.setSpacing(6)

        self.log_title_lbl = QLabel(("Rapport d'exécution" if self.lang == "fr" else "تقرير خطوات المعالجة"), self.log_panel)
        self.log_title_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #1e3a8a;")
        log_panel_lay.addWidget(self.log_title_lbl)

        self.log_view = QTextEdit(self.log_panel)
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(130)
        self.log_view.setMaximumHeight(240)
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 12px;
                padding: 8px;
            }
        """)
        log_panel_lay.addWidget(self.log_view)
        left_lay.addWidget(self.log_panel)

        # ── 2. RIGHT PANEL : CONTRACT EDITOR & LEGAL AUDIT (WITH SCROLL) ──────
        right_panel = QFrame(master_panel)
        right_panel.setFrameShape(QFrame.Shape.NoFrame)
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(15)
        master_lay.addWidget(right_panel)

        # Header preview title
        self.preview_header = QLabel(("Aperçu officiel du contrat" if self.lang == "fr" else "معاينة العقد الرسمي المحرر"), right_panel)
        self.preview_header.setStyleSheet("font-weight: 800; font-size: 14px; color: #1e3a8a;")
        right_lay.addWidget(self.preview_header)

        # En-tête officiel du Cabinet Zarai HTML
        self.header_label = QLabel(right_panel)
        self.header_label.setText(contract_templates.NOTARY_HEADER_HTML)
        self.header_label.setTextFormat(Qt.TextFormat.RichText)
        self.header_label.setWordWrap(True)
        right_lay.addWidget(self.header_label)

        # Center Title
        self.contract_title_lbl = QLabel("عقد بيع توثيقي", right_panel)
        self.contract_title_lbl.setStyleSheet("font-weight: 900; font-size: 16px; color: #0f172a;")
        self.contract_title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_lay.addWidget(self.contract_title_lbl)

        # Text Editor
        self.editor = QTextEdit(right_panel)
        self.editor.setObjectName("ContractEditor")
        self.editor.setMinimumHeight(450) # Grant generous height to editor
        self.editor.setStyleSheet("""
            QTextEdit#ContractEditor {
                background-color: #ffffff;
                border: 2px solid #cbd5e1;
                border-radius: 8px;
                color: #0f172a;
                font-size: 14px;
                font-family: 'Courier New', monospace;
                padding: 15px;
                line-height: 1.6;
            }
        """)
        self.editor.textChanged.connect(self.on_editor_text_changed)
        right_lay.addWidget(self.editor)

        # Pied de page officiel du Cabinet Zarai HTML
        self.footer_label = QLabel(right_panel)
        self.footer_label.setText(contract_templates.NOTARY_FOOTER_HTML)
        self.footer_label.setTextFormat(Qt.TextFormat.RichText)
        self.footer_label.setWordWrap(True)
        right_lay.addWidget(self.footer_label)

        self.copy_btn = QPushButton(("Copier le texte" if self.lang == "fr" else "📋 نسخ النص"), right_panel)
        self.copy_btn.setProperty("class", "SecondaryButton")
        self.copy_btn.clicked.connect(self.copy_contract_text)
        right_lay.addWidget(self.copy_btn)

        # Exports
        exports_box = QHBoxLayout()
        self.export_word_btn = QPushButton("📄 تحميل Word", right_panel)
        self.export_word_btn.setProperty("class", "PrimaryButton")
        self.export_word_btn.clicked.connect(self.export_word)

        self.export_pdf_btn = QPushButton("📕 تحميل PDF", right_panel)
        self.export_pdf_btn.setProperty("class", "SecondaryButton")
        self.export_pdf_btn.clicked.connect(self.export_pdf)
        
        exports_box.addWidget(self.export_word_btn)
        exports_box.addWidget(self.export_pdf_btn)
        right_lay.addLayout(exports_box)

        # Multiple Archiving
        right_lay.addWidget(QLabel(("<b>Archiver le contrat dans les dossiers clients :</b>" if self.lang == "fr" else "<b>أرشفة وحفظ العقد في ملفات الحرفاء :</b>")))
        
        self.client_search_input = QLineEdit(right_panel)
        self.client_search_input.setStyleSheet("QLineEdit { padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px; }")
        self.client_search_input.textChanged.connect(self.filter_clients)
        right_lay.addWidget(self.client_search_input)

        self.client_count_lbl = QLabel("", right_panel)
        self.client_count_lbl.setWordWrap(True)
        self.client_count_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        right_lay.addWidget(self.client_count_lbl)

        self.add_extra_client_btn = QPushButton("➕ إضافة حريف من الأرشيف", right_panel)
        self.add_extra_client_btn.setFixedHeight(34)
        self.add_extra_client_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.add_extra_client_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0fdf4;
                color: #15803d;
                border: 1.5px dashed #86efac;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #dcfce7;
                border-color: #4ade80;
            }
        """)
        self.add_extra_client_btn.clicked.connect(self.open_add_extra_client_dialog)
        right_lay.addWidget(self.add_extra_client_btn)

        self.archive_list = QListWidget(right_panel)
        self.archive_list.setMinimumHeight(120)
        self.archive_list.setStyleSheet("QListWidget { border: 1px solid #cbd5e1; border-radius: 6px; background: #ffffff; }")
        self.archive_list.itemChanged.connect(self.on_archive_item_changed)
        right_lay.addWidget(self.archive_list)

        self.archive_btn = QPushButton("💾 أرشفة وحفظ العقد", right_panel)
        self.archive_btn.setProperty("class", "PrimaryButton")
        self.archive_btn.clicked.connect(self.archive_to_clients)
        right_lay.addWidget(self.archive_btn)

        master_scroll.setWidget(master_panel)
        self.main_layout.addWidget(master_scroll)
        
        # Initial draw
        self.rebuild_parties_ui()

    # ── IA Provider selection ──
    def filter_clients(self, text):
        q = (text or "").strip()
        if not q:
            self.refresh_chosen_clients_archive_list()
            return

        search_results = reception.search_clients_summary(q)
        checked_cids = set()
        for i in range(self.archive_list.count()):
            item = self.archive_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                cid = item.data(Qt.ItemDataRole.UserRole)
                if cid:
                    checked_cids.add(cid)

        self.archive_list.clear()

        # Keep already checked/chosen clients checked
        for cid in checked_cids:
            c = reception.get_client_by_id(cid)
            if c:
                fn = c.get("full_name") or f"{c.get('prenom','')} {c.get('nom','')}".strip()
                cin_num = c.get("cin_number", "—")
                item = QListWidgetItem(f"✓ {fn} (CIN: {cin_num}) [محدد]")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, cid)
                self.archive_list.addItem(item)

        # Add search results
        for c in search_results:
            cid = c.get("client_id")
            if cid in checked_cids:
                continue
            fn = c.get("name") or f"{c.get('prenom','')} {c.get('nom','')}".strip()
            item = QListWidgetItem(f"{fn} (CIN: {c.get('cin', '—')})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, cid)
            self.archive_list.addItem(item)

        try:
            total = reception.count_clients()
        except Exception:
            total = 0
        shown = len(search_results)
        if hasattr(self, "client_count_lbl"):
            self.client_count_lbl.setText(f"نتائج البحث في أرشيف الحرفاء: {shown} من مجموع {total} حريف")
            self.client_count_lbl.setStyleSheet("color: #1e40af; font-size: 11px; font-weight: bold;")

    # -- Party cards ---------------------------------------------------------
    # Each party used to get its own QComboBox filled one addItem() at a time with all
    # 1,000 clients, and the whole two-column layout was destroyed and rebuilt on every
    # call - from seven call sites, including every ID-card upload. That cost 331 ms with
    # two parties and 7.2 s with twelve, which is an ordinary inheritance deed.
    #
    # Now one QStandardItemModel is built once per client list and shared by every combo
    # through setModel(), and a call that does not change the structure only refreshes
    # the existing widgets instead of recreating them.

    def _ensure_client_model(self):
        """Builds the single client model shared by every party combo box."""
        signature = (id(self.clients_list), len(self.clients_list))
        if (getattr(self, "_client_model", None) is not None
                and getattr(self, "_client_model_signature", None) == signature):
            return self._client_model

        model = QStandardItemModel(self)
        first = QStandardItem("-- اختيار حريف مسجل --")
        first.setData("", Qt.ItemDataRole.UserRole)
        model.appendRow(first)
        for c in self.clients_list:
            item = QStandardItem(f"{c['name']} (CIN: {c['cin']})")
            item.setData(c["id"], Qt.ItemDataRole.UserRole)
            model.appendRow(item)

        self._client_model = model
        self._client_model_signature = signature
        return model

    def _select_client_in_combo(self, combo, client_id):
        """Selects a client without firing the change handler."""
        target = 0
        if client_id:
            found = combo.findData(client_id, Qt.ItemDataRole.UserRole)
            if found >= 0:
                target = found
        if combo.currentIndex() != target:
            blocked = combo.blockSignals(True)
            combo.setCurrentIndex(target)
            combo.blockSignals(blocked)

    def _build_party_card(self, p_type, idx, party, singular, on_selected):
        """Creates one party card, returning it with the widgets that need refreshing."""
        card = QFrame()
        card.setObjectName("PartyCard")
        # Scoped: unscoped, this also repainted the two upload buttons inside it.
        card.setStyleSheet("QFrame#PartyCard { background-color: #ffffff; border-radius: 8px;"
                           " padding: 8px; border: 1.5px solid #cbd5e1; }")
        card_lay = QVBoxLayout(card)

        lbl_title = QLabel(f"<b>{singular} {idx+1} :</b>")
        card_lay.addWidget(lbl_title)

        combo = QComboBox(card)
        combo.setModel(self._ensure_client_model())
        self._select_client_in_combo(combo, party["client_id"])
        combo.currentIndexChanged.connect(lambda _, i=idx, cb=combo: on_selected(i, cb))
        card_lay.addWidget(QLabel("حريف مسجل :"))
        card_lay.addWidget(combo)

        f_btn = QPushButton(("Charger le recto" if self.lang == "fr" else "رفع الوجه الأمامي"), card)
        f_btn.setProperty("class", "SecondaryButton")
        f_btn.clicked.connect(lambda _, i=idx: self.upload_cin_image(p_type, i, "front"))
        card_lay.addWidget(f_btn)

        f_lbl = QLabel(party["front_lbl"])
        f_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        card_lay.addWidget(f_lbl)

        b_btn = QPushButton(("Charger le verso" if self.lang == "fr" else "رفع الوجه الخلفي"), card)
        b_btn.setProperty("class", "SecondaryButton")
        b_btn.clicked.connect(lambda _, i=idx: self.upload_cin_image(p_type, i, "back"))
        card_lay.addWidget(b_btn)

        b_lbl = QLabel(party["back_lbl"])
        b_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        card_lay.addWidget(b_lbl)

        both_btn = QPushButton(("Charger 2 faces (1 seule photo)" if self.lang == "fr" else "📸 رفع الوجهين في صورة واحدة (صفحة واحدة)"), card)
        both_btn.setStyleSheet("background-color: #f0fdf4; color: #15803d; border: 1.5px dashed #86efac; font-size: 11px; font-weight: bold; padding: 5px 8px; border-radius: 5px;")
        both_btn.clicked.connect(lambda _, i=idx: self.upload_cin_image(p_type, i, "both"))
        card_lay.addWidget(both_btn)

        return card, {"title": lbl_title, "combo": combo, "front": f_lbl, "back": b_lbl}

    def _refresh_parties_in_place(self, roles):
        """Updates the existing cards. Returns False when a full rebuild is required."""
        cards = getattr(self, "_party_cards", None)
        if not cards or getattr(self, "_party_roles", None) != roles:
            return False
        if getattr(self, "_party_model_signature", None) != getattr(self, "_client_model_signature", None):
            return False
        for p_type, parties in (("p1", self.p1_parties), ("p2", self.p2_parties)):
            if len(cards.get(p_type, [])) != len(parties):
                return False
        for p_type, parties, singular in (("p1", self.p1_parties, roles[0]),
                                          ("p2", self.p2_parties, roles[2])):
            for idx, party in enumerate(parties):
                w = cards[p_type][idx]
                w["title"].setText(f"<b>{singular} {idx+1} :</b>")
                w["front"].setText(party["front_lbl"])
                w["back"].setText(party["back_lbl"])
                self._select_client_in_combo(w["combo"], party["client_id"])
        return True

    def rebuild_parties_ui(self):
        p1_sing, p1_plur, p2_sing, p2_plur, allow_multi = contract_templates.get_party_role_names(self.selected_contract_type)
        roles = (p1_sing, p1_plur, p2_sing, p2_plur, allow_multi)

        self._ensure_client_model()
        if self._refresh_parties_in_place(roles):
            return

        self.clear_layout(self.col_p1_lay)
        self.clear_layout(self.col_p2_lay)
        self._party_cards = {"p1": [], "p2": []}

        for p_type, parties, lay, container, plural, singular, on_sel in (
            ("p1", self.p1_parties, self.col_p1_lay, self.col_p1_container,
             p1_plur, p1_sing, self.on_p1_client_selected),
            ("p2", self.p2_parties, self.col_p2_lay, self.col_p2_container,
             p2_plur, p2_sing, self.on_p2_client_selected),
        ):
            side = "الطرف الأول" if p_type == "p1" else "الطرف الثاني"
            title_lbl = QLabel(f" {plural} ({side}) :")
            title_lbl.setStyleSheet("font-weight: bold; color: #1e3a8a;")
            lay.addWidget(title_lbl)

            for idx, party in enumerate(parties):
                card, widgets = self._build_party_card(p_type, idx, party, singular, on_sel)
                lay.addWidget(card)
                self._party_cards[p_type].append(widgets)

            if allow_multi:
                btn_lay = QHBoxLayout()
                add_btn = QPushButton("إضافة آخر", container)
                add_btn.setProperty("class", "SecondaryButton")
                add_btn.clicked.connect(lambda _=False, t=p_type: self.add_party(t))
                rem_btn = QPushButton("حذف", container)
                rem_btn.setProperty("class", "SecondaryButton")
                rem_btn.clicked.connect(lambda _=False, t=p_type: self.remove_party(t))
                btn_lay.addWidget(add_btn)
                btn_lay.addWidget(rem_btn)
                lay.addLayout(btn_lay)

        self._party_roles = roles
        self._party_model_signature = self._client_model_signature

    def clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clear_layout(item.layout())

    def add_party(self, p_type):
        if p_type == "p1":
            self.p1_parties.append({"client_id": "", "front_bytes": None, "back_bytes": None, "front_lbl": "لا يوجد", "back_lbl": "لا يوجد"})
        else:
            self.p2_parties.append({"client_id": "", "front_bytes": None, "back_bytes": None, "front_lbl": "لا يوجد", "back_lbl": "لا يوجد"})
        self.rebuild_parties_ui()

    def remove_party(self, p_type):
        if p_type == "p1" and len(self.p1_parties) > 1:
            self.p1_parties.pop()
        elif p_type == "p2" and len(self.p2_parties) > 1:
            self.p2_parties.pop()
        self.rebuild_parties_ui()

    def update_dossiers_combo(self):
        if not hasattr(self, "dossier_combo"):
            return
        try:
            client_ids = []
            for p in self.p1_parties + self.p2_parties:
                cid = p.get("client_id")
                if cid and cid not in client_ids:
                    client_ids.append(cid)

            current_data = self.dossier_combo.currentData()
            self.dossier_combo.clear()
            self.dossier_combo.addItem("-- إنشاء ملف جديد لهذا العقد --" if self.lang == "ar" else "-- Nouveau dossier --", "")

            added_cases = set()
            for cid in client_ids:
                client = reception.get_client_by_id(cid) or {}
                c_name = client.get("full_name") or f"حريف {cid}"
                cases = reception.get_client_cases(cid)
                for cs in cases:
                    case_id = cs.get("case_id")
                    if case_id and case_id not in added_cases:
                        added_cases.add(case_id)
                        title = cs.get("title") or cs.get("service_type") or "ملف"
                        status = cs.get("status", "جديد")
                        self.dossier_combo.addItem(f"ملف عدد {case_id} — {title} ({c_name} | {status})", case_id)

            idx = self.dossier_combo.findData(current_data)
            if idx >= 0:
                self.dossier_combo.setCurrentIndex(idx)
        except Exception as ex:
            print("update_dossiers_combo error:", ex)

    def on_dossier_combo_changed(self, idx=None):
        if not hasattr(self, "dossier_combo") or not hasattr(self, "var_dossier_num"):
            return
        selected_id = self.dossier_combo.currentData()
        if selected_id:
            self.var_dossier_num.setText(str(selected_id))
            self.var_dossier_num.setEnabled(False)
        else:
            self.var_dossier_num.clear()
            self.var_dossier_num.setEnabled(True)

    def on_p1_client_selected(self, idx, combo=None):
        sender = combo if isinstance(combo, QComboBox) else self.sender()
        if isinstance(sender, QComboBox):
            cid = sender.currentData()
            self.p1_parties[idx]["client_id"] = cid
            if cid:
                client = reception.get_client_by_id(cid)
                if client:
                    while len(self.p1_extracted) <= idx:
                        self.p1_extracted.append({})
                    self.p1_extracted[idx] = {
                        "full_name": client.get("full_name") or f"{client.get('prenom','')} {client.get('nom','')}".strip(),
                        "cin_number": client.get("cin_number", ""),
                        "issue_date": client.get("cin_issue_date") or client.get("cin_date_place", ""),
                        "birth_date": client.get("birth_date", ""),
                        "birth_place": client.get("birth_place", ""),
                        "job": client.get("profession", ""),
                        "address": client.get("address", ""),
                        "father_name": client.get("father_name", ""),
                        "grandfather_name": client.get("grandfather_name", ""),
                    }
                    if idx == 0:
                        self.contract_vars["party1_name"] = self.p1_extracted[0]["full_name"]
                        self.contract_vars["party1_cin"] = self.p1_extracted[0]["cin_number"]
                        self.contract_vars["party1_job"] = self.p1_extracted[0]["job"]
                        self.contract_vars["party1_addr"] = self.p1_extracted[0]["address"]
                        self.update_ui_fields_from_state()
            else:
                if idx < len(self.p1_extracted):
                    self.p1_extracted[idx] = {}
            self.update_dossiers_combo()
            self.refresh_contract_preview_text()
            self.refresh_chosen_clients_archive_list()

    def on_p2_client_selected(self, idx, combo=None):
        sender = combo if isinstance(combo, QComboBox) else self.sender()
        if isinstance(sender, QComboBox):
            cid = sender.currentData()
            self.p2_parties[idx]["client_id"] = cid
            if cid:
                client = reception.get_client_by_id(cid)
                if client:
                    while len(self.p2_extracted) <= idx:
                        self.p2_extracted.append({})
                    self.p2_extracted[idx] = {
                        "full_name": client.get("full_name") or f"{client.get('prenom','')} {client.get('nom','')}".strip(),
                        "cin_number": client.get("cin_number", ""),
                        "issue_date": client.get("cin_issue_date") or client.get("cin_date_place", ""),
                        "birth_date": client.get("birth_date", ""),
                        "birth_place": client.get("birth_place", ""),
                        "job": client.get("profession", ""),
                        "address": client.get("address", ""),
                        "father_name": client.get("father_name", ""),
                        "grandfather_name": client.get("grandfather_name", ""),
                    }
                    if idx == 0:
                        self.contract_vars["party2_name"] = self.p2_extracted[0]["full_name"]
                        self.contract_vars["party2_cin"] = self.p2_extracted[0]["cin_number"]
                        self.contract_vars["party2_job"] = self.p2_extracted[0]["job"]
                        self.contract_vars["party2_addr"] = self.p2_extracted[0]["address"]
                        self.update_ui_fields_from_state()
            else:
                if idx < len(self.p2_extracted):
                    self.p2_extracted[idx] = {}
            self.update_dossiers_combo()
            self.refresh_contract_preview_text()
            self.refresh_chosen_clients_archive_list()

    def upload_cin_image(self, p_type, idx, face):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Choisir la photo CIN / اختيار بطاقة التعريف", "", "Images (*.jpg *.jpeg *.png *.webp)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "rb") as f:
                img_bytes = f.read()
        except Exception as ex:
            QMessageBox.warning(self, "بطاقة التعريف", f"تعذّر فتح الملف المختار:\n{ex}")
            return

        check = ocr_engine.inspect_card_image(img_bytes)
        if not check.get("ok"):
            QMessageBox.warning(
                self, "بطاقة التعريف",
                f"{check.get('error')}\n\nالملف: {Path(file_path).name}"
            )
            return

        fname = Path(file_path).name
        p_list = self.p1_parties if p_type == "p1" else self.p2_parties
        if face == "front":
            p_list[idx]["front_bytes"] = img_bytes
            p_list[idx]["front_lbl"] = fname
        elif face == "back":
            p_list[idx]["back_bytes"] = img_bytes
            p_list[idx]["back_lbl"] = fname
        elif face == "both":
            p_list[idx]["front_bytes"] = img_bytes
            p_list[idx]["back_bytes"] = None
            p_list[idx]["front_lbl"] = f"الوجهان معاً: {fname}"
            p_list[idx]["back_lbl"] = "(صورة واحدة تحتوي على الوجهين)"

        # Save CIN photo to client attachments if client is selected
        cid = p_list[idx].get("client_id")
        if cid:
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            reception.save_client_document(cid, img_bytes, f"بطاقة_تعريف_{fname}_{stamp}.jpg")

        self.rebuild_parties_ui()

        # Always reload AI settings first so ocr_api_key is guaranteed fresh on upload
        self.reload_ai_engine()

        # Every upload used to fire a full scan, so a card given front-then-back
        # cost TWO calls: one on the front alone, then one on both faces whose
        # result overwrote the first. The front-only call was pure waste — a
        # measured ~50 s each, and it also read no job and no address, since
        # those are printed on the back.
        #
        # The scan now waits for the uploads to settle. Adding the back within
        # the window restarts the delay, so the pair leaves as a single call
        # carrying both faces.
        if p_list[idx].get("front_bytes") and self.ocr_api_key:
            self._schedule_background_cin_ocr(p_type, idx)

    # How long to wait for a second face before scanning. Long enough to pick a
    # file from a dialog, short enough that the pre-scan still finishes while the
    # notary chooses the act type.
    OCR_SETTLE_MS = 2000

    def _schedule_background_cin_ocr(self, p_type, idx):
        """Runs one scan once the uploads for this party have stopped arriving."""
        from PySide6.QtCore import QTimer
        if not hasattr(self, "_ocr_timers"):
            self._ocr_timers = {}
        key = (p_type, idx)
        timer = self._ocr_timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: self.trigger_background_cin_ocr(*k))
            self._ocr_timers[key] = timer
        # restart: a second face arriving cancels the scan the first one queued
        timer.start(self.OCR_SETTLE_MS)

    def trigger_background_cin_ocr(self, p_type, idx):
        p_list = self.p1_parties if p_type == "p1" else self.p2_parties
        party = p_list[idx]
        front_b = party.get("front_bytes")
        back_b = party.get("back_bytes")
        if not front_b:
            return

        import time, sys
        t_start = time.perf_counter()
        sys.stdout.write(f"\n[TIMING] ⚡ Instant Background CIN Pre-OCR Started on Upload for {p_type} Card {idx+1}...\n")
        sys.stdout.flush()

        def _do_ocr():
            try:
                import cin_extractor
                res = cin_extractor.extract_cin_dual_faces(
                    front_b, back_b, self.ocr_api_key, self.ocr_model, self.ocr_provider
                )
                dur = time.perf_counter() - t_start
                if res.get("success") and res.get("data", {}).get("full_name"):
                    party["extracted"] = res["data"]
                    d = res["data"]
                    faces_str = "Front + Back Dual-Face" if (front_b and back_b) else ("Front Only" if front_b else "Back Only")
                    job_str = d.get('job') or "لم يُذكر"
                    addr_str = d.get('address') or "لم يُذكر"
                    sys.stdout.write(f"[TIMING] ✅ Background CIN Pre-OCR ({faces_str}) Finished in {dur:.2f}s! Name={d.get('full_name')} | Job={job_str} | Address={addr_str}\n")
                    sys.stdout.flush()
                else:
                    sys.stdout.write(f"[TIMING] ⚠️ Background CIN Pre-OCR Failed in {dur:.2f}s: {res.get('error')}\n")
                    sys.stdout.flush()
            except Exception as ex:
                sys.stdout.write(f"[TIMING] ❌ Background CIN Pre-OCR Exception: {ex}\n")
                sys.stdout.flush()

        import threading
        t = threading.Thread(target=_do_ocr, daemon=True)
        party["ocr_thread"] = t
        t.start()

    # ── Clients list loader ──
    CLIENT_LIST_PAGE = 1000

    def load_clients_list(self):
        """Loads the most recent clients for party dropdowns, and initializes chosen archive list."""
        try:
            clients = reception.get_all_clients_summary(limit=self.CLIENT_LIST_PAGE)
        except reception.DataUnavailable:
            clients = []
        self.clients_list = [{
            "id": c.get("client_id"),
            "name": c.get("full_name"),
            "cin": c.get("cin_number", "—")
        } for c in clients]
        self.rebuild_parties_ui()
        self.refresh_chosen_clients_archive_list()

    def on_archive_item_changed(self, item):
        if not item or self.archive_list.signalsBlocked():
            return
        if item.checkState() == Qt.CheckState.Unchecked:
            row = self.archive_list.row(item)
            if row >= 0:
                self.archive_list.blockSignals(True)
                self.archive_list.takeItem(row)
                self.archive_list.blockSignals(False)

            checked_count = sum(
                1 for i in range(self.archive_list.count())
                if self.archive_list.item(i) and self.archive_list.item(i).checkState() == Qt.CheckState.Checked
            )
            if hasattr(self, "client_count_lbl"):
                if checked_count > 0:
                    self.client_count_lbl.setText(f"أطراف العقد المحددة تلقائياً ({checked_count}) — يمكنك البحث في الأرشيف لإضافة حريف آخر")
                    self.client_count_lbl.setStyleSheet("color: #059669; font-size: 11px; font-weight: bold;")
                else:
                    self.client_count_lbl.setText("لم يتم تحديد أطراف بعد — يرجى اختيار الحرفاء أو رفع بطاقات التعريف")
                    self.client_count_lbl.setStyleSheet("color: #64748b; font-size: 11px;")

    def open_add_extra_client_dialog(self, *args):
        try:
            from ui.dialogs.client_search_dialog import ClientSearchDialog
            dlg = ClientSearchDialog(self, title="اختيار حريف إضافي لأرشفة العقد بملفه")
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_client:
                c = dlg.selected_client
                cid = str(c.get("client_id", "")).strip() if isinstance(c, dict) else ""
                if not cid:
                    return

                self.archive_list.blockSignals(True)
                already_in = False
                for i in range(self.archive_list.count()):
                    item = self.archive_list.item(i)
                    if item and str(item.data(Qt.ItemDataRole.UserRole)).strip() == cid:
                        item.setCheckState(Qt.CheckState.Checked)
                        already_in = True
                        break

                if not already_in:
                    fn = c.get("full_name") or f"{c.get('prenom','')} {c.get('nom','')}".strip()
                    cin_num = c.get("cin_number", "—")
                    item = QListWidgetItem(f"✓ {fn} (CIN: {cin_num}) [حريف إضافي]")
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)  # AUTO-TICKED!
                    item.setData(Qt.ItemDataRole.UserRole, cid)
                    self.archive_list.addItem(item)
                self.archive_list.blockSignals(False)

                checked_count = sum(
                    1 for i in range(self.archive_list.count())
                    if self.archive_list.item(i) and self.archive_list.item(i).checkState() == Qt.CheckState.Checked
                )
                if hasattr(self, "client_count_lbl"):
                    self.client_count_lbl.setText(f"أطراف العقد والحرفاء المحددين تلقائياً ({checked_count})")
                    self.client_count_lbl.setStyleSheet("color: #059669; font-size: 11px; font-weight: bold;")
        except Exception as ex:
            print("open_add_extra_client_dialog error:", ex)

    def refresh_chosen_clients_archive_list(self):
        """
        Populates the archive_list ONLY with the specific clients chosen or extracted
        for this contract, and automatically ticks (checks) them by default.
        """
        if not hasattr(self, "archive_list"):
            return

        self.archive_list.blockSignals(True)
        self.archive_list.clear()

        # Collect chosen client IDs from all active contract sources, strictly deduplicated by string ID
        chosen_client_ids = []
        seen = set()

        def add_cid(raw_cid):
            if raw_cid is None:
                return
            s_id = str(raw_cid).strip()
            if s_id and s_id not in seen:
                seen.add(s_id)
                chosen_client_ids.append(s_id)

        # 1. From dropdown / party card selections
        for p in self.p1_parties + self.p2_parties:
            add_cid(p.get("client_id"))

        # 2. From extracted party records (p1_extracted, p2_extracted)
        for p_list in (getattr(self, "p1_extracted", []), getattr(self, "p2_extracted", [])):
            for ext in p_list:
                cin = (ext.get("cin_number") or "").strip()
                fn = (ext.get("full_name") or "").strip()
                if cin or fn:
                    c = reception.find_client_by_cin_or_name(cin_number=cin, full_name=fn)
                    if c and c.get("client_id"):
                        add_cid(c["client_id"])

        # 3. From contract_vars CIN numbers or names
        for prefix in ("party1", "party2"):
            cin = (self.contract_vars.get(f"{prefix}_cin") or "").strip()
            fn = (self.contract_vars.get(f"{prefix}_name") or "").strip()
            if cin or fn:
                c = reception.find_client_by_cin_or_name(cin_number=cin, full_name=fn)
                if c and c.get("client_id"):
                    add_cid(c["client_id"])

        # Build list items for chosen clients ONLY, auto-ticked (Checked)
        items_added = 0
        for cid in chosen_client_ids:
            c = reception.get_client_by_id(cid)
            if c:
                fn = c.get("full_name") or f"{c.get('prenom','')} {c.get('nom','')}".strip() or f"حريف {cid}"
                cin_num = c.get("cin_number", "—")
                item = QListWidgetItem(f"✓ {fn} (CIN: {cin_num})")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)  # AUTO-TICKED!
                item.setData(Qt.ItemDataRole.UserRole, cid)
                self.archive_list.addItem(item)
                items_added += 1

        self.archive_list.blockSignals(False)

        if hasattr(self, "client_count_lbl"):
            if items_added > 0:
                self.client_count_lbl.setText(f"أطراف العقد المحددة تلقائياً ({items_added}) — يمكنك البحث في الأرشيف لإضافة حريف آخر")
                self.client_count_lbl.setStyleSheet("color: #059669; font-size: 11px; font-weight: bold;")
            else:
                self.client_count_lbl.setText("لم يتم تحديد أطراف بعد — يرجى اختيار الحرفاء أو رفع بطاقات التعريف")
                self.client_count_lbl.setStyleSheet("color: #64748b; font-size: 11px;")

    def _populate_client_list(self, clients, searching: bool):
        self.clients_list = []
        for c in clients:
            self.clients_list.append({
                "id": c.get("client_id"),
                "name": c.get("full_name"),
                "cin": c.get("cin_number", "—")
            })
        self.refresh_chosen_clients_archive_list()

    def populate_contract_types(self):
        self.contract_menu = QMenu(self)
        self.contract_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        menu_qss = """
            QMenu {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QMenu::item {
                padding: 8px 24px 8px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #e0f2fe;
                color: #0369a1;
            }
        """
        self.contract_menu.setStyleSheet(menu_qss)

        for cat_name, contracts in contract_templates.CONTRACT_CATEGORIES.items():
            sub_menu = self.contract_menu.addMenu(cat_name)
            sub_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            sub_menu.setStyleSheet(menu_qss)
            for c in contracts:
                action = sub_menu.addAction(c)
                action.triggered.connect(lambda checked=False, contract=c: self.select_contract_type(contract))

        self.type_btn.setMenu(self.contract_menu)
        if hasattr(self, 'selected_contract_type') and self.selected_contract_type:
            self.type_btn.setText(f"  {self.selected_contract_type}  ")
        else:
            self.select_contract_type("عقد بيع")

    def select_contract_type(self, selected_type: str):
        if not selected_type:
            return
        self.selected_contract_type = selected_type
        self.type_btn.setText(f"  {selected_type}  ")
        self.contract_title_lbl.setText(selected_type)

        self.contract_vars = contract_templates.get_default_variables(selected_type)
        self.contract_vars["contract_type"] = selected_type

        self.update_contract_date_state()
        self.update_ui_fields_from_state()
        self.refresh_contract_preview_text()
        self.rebuild_parties_ui()

    def update_office_header(self):
        if hasattr(self, "header_label"):
            import contract_templates
            self.header_label.setText(contract_templates.NOTARY_HEADER_HTML)

    def showEvent(self, event):
        super().showEvent(event)
        self.update_office_header()
        self.update_contract_date_state()
        self.refresh_contract_preview_text()

    def on_date_mode_changed(self):
        is_custom = hasattr(self, "radio_date_custom") and self.radio_date_custom.isChecked()
        if hasattr(self, "custom_date_edit"):
            self.custom_date_edit.setEnabled(is_custom)
        self.update_contract_date_state()

    def on_custom_date_changed(self, qdate):
        self.update_contract_date_state()

    def update_contract_date_state(self):
        import datetime, contract_templates
        if hasattr(self, "radio_date_custom") and self.radio_date_custom.isChecked():
            qd = self.custom_date_edit.date()
            py_date = datetime.date(qd.year(), qd.month(), qd.day())
        else:
            py_date = datetime.date.today()

        date_info = contract_templates.get_current_arabic_date_info(dt=py_date)
        self.contract_vars["date_info"] = date_info
        self.contract_vars["custom_date"] = py_date
        
        if hasattr(self, "lbl_date_preview"):
            self.lbl_date_preview.setText(f"التاريخ الرسمي المصرح به في العقد: {date_info['full_date_text_no_time']}")

        if hasattr(self, "editor"):
            self.refresh_contract_preview_text()

    def on_contract_type_changed(self):
        pass

    def update_ui_fields_from_state(self):
        for attr in ["var_p1_name", "var_p1_cin", "var_p1_job", "var_p1_addr",
                     "var_p2_name", "var_p2_cin", "var_p2_job", "var_p2_addr",
                     "var_price_num", "var_price_words", "var_prop_title",
                     "var_titre_foncier", "var_titre_gov", "var_prop_location", "var_prop_area"]:
            w = getattr(self, attr, None)
            if w is not None:
                key = attr.replace("var_", "")
                w.setText(self.contract_vars.get(key, ""))

        for attr in ["var_property_desc", "var_ownership_origin"]:
            w = getattr(self, attr, None)
            if w is not None:
                key = attr.replace("var_", "")
                w.setPlainText(self.contract_vars.get(key, ""))

    def pull_state_from_ui_fields(self):
        import re
        widget_map_text = [
            ("party1_name", getattr(self, "var_p1_name", None)),
            ("party1_cin", getattr(self, "var_p1_cin", None)),
            ("party1_job", getattr(self, "var_p1_job", None)),
            ("party1_addr", getattr(self, "var_p1_addr", None)),
            ("party2_name", getattr(self, "var_p2_name", None)),
            ("party2_cin", getattr(self, "var_p2_cin", None)),
            ("party2_job", getattr(self, "var_p2_job", None)),
            ("party2_addr", getattr(self, "var_p2_addr", None)),
            ("price_num", getattr(self, "var_price_num", None)),
            ("price_words", getattr(self, "var_price_words", None)),
            ("property_title", getattr(self, "var_prop_title", None)),
            ("titre_foncier", getattr(self, "var_titre_foncier", None)),
            ("titre_gov", getattr(self, "var_titre_gov", None)),
            ("property_location", getattr(self, "var_prop_location", None)),
            ("property_area", getattr(self, "var_prop_area", None)),
        ]
        for key, widget in widget_map_text:
            if widget is not None:
                val = widget.text().strip()
                if val:
                    self.contract_vars[key] = val

        for key, widget in [
            ("property_desc", getattr(self, "var_property_desc", None)),
            ("ownership_origin", getattr(self, "var_ownership_origin", None)),
        ]:
            if widget is not None:
                val = widget.toPlainText().strip()
                if val:
                    self.contract_vars[key] = val

        p_num = self.contract_vars.get("price_num", "").strip()
        p_words = self.contract_vars.get("price_words", "").strip()
        if p_num and (not p_words or re.match(r"^[\d.,\s]+$", p_words)):
            gen_words = contract_templates.number_to_arabic_words(p_num)
            if gen_words:
                if "دينار" not in gen_words and "مليم" not in gen_words:
                    gen_words += " دينار"
                self.contract_vars["price_words"] = gen_words
                w_pw = getattr(self, "var_price_words", None)
                if w_pw is not None:
                    w_pw.setText(gen_words)

    def _build_party_list(self, party_slots, extracted_list, prefix, label_ar):
        """
        Builds the party records for the contract template.

        The first party's editable fields come from the form, but every other field —
        CIN issue date, birth date, birth place — is preserved from what the pipeline
        actually extracted. Parties beyond the first keep their extracted record in
        full; only a party with no data at all falls back to a blank placeholder.
        """
        out = []
        for idx in range(len(party_slots)):
            extracted = dict(extracted_list[idx]) if idx < len(extracted_list) and extracted_list[idx] else {}

            if idx == 0:
                # Form fields win for the four editable values; everything else survives.
                extracted.update({
                    "full_name": self.contract_vars.get(f"{prefix}_name") or extracted.get("full_name", ""),
                    "cin_number": self.contract_vars.get(f"{prefix}_cin") or extracted.get("cin_number", ""),
                    "job": self.contract_vars.get(f"{prefix}_job") or extracted.get("job", ""),
                    "address": self.contract_vars.get(f"{prefix}_addr") or extracted.get("address", ""),
                })
                for form_key, rec_key in (
                    (f"{prefix}_cin_date", "issue_date"),
                    (f"{prefix}_birthdate", "birth_date"),
                    (f"{prefix}_birthplace", "birth_place"),
                ):
                    if self.contract_vars.get(form_key):
                        extracted[rec_key] = self.contract_vars.get(form_key)

            if not extracted.get("full_name"):
                # No data yet for this party: leave blanks for the notary to fill by hand
                # rather than writing a fake name such as "الطرف الأول 2" into the deed.
                extracted.setdefault("full_name", "........................")
                extracted.setdefault("cin_number", "........")
            out.append(extracted)
        return out

    def refresh_contract_preview_text(self):
        self.pull_state_from_ui_fields()

        party1_list = self._build_party_list(self.p1_parties, self.p1_extracted, "party1", "الطرف الأول")
        party2_list = self._build_party_list(self.p2_parties, self.p2_extracted, "party2", "الطرف الثاني")

        w1_w = getattr(self, "var_witness1_name", None)
        w1_name = w1_w.text().strip() if w1_w is not None else ""
        w1_cin_w = getattr(self, "var_witness1_cin", None)
        w1_cin = w1_cin_w.text().strip() if w1_cin_w is not None else ""
        w1_data = {"name": w1_name, "cin": w1_cin} if w1_name else None

        w2_w = getattr(self, "var_witness2_name", None)
        w2_name = w2_w.text().strip() if w2_w is not None else ""
        w2_cin_w = getattr(self, "var_witness2_cin", None)
        w2_cin = w2_cin_w.text().strip() if w2_cin_w is not None else ""
        w2_data = {"name": w2_data, "cin": w2_cin} if w2_name else None

        procuration_txt = self.procuration_input.toPlainText().strip() if hasattr(self, "procuration_input") and self.procuration_input else ""

        base_text = contract_templates.build_multi_party_contract_text(
            contract_type=self.selected_contract_type,
            party1_list=party1_list,
            party2_list=party2_list,
            procuration_text=procuration_txt,
            property_desc=self.contract_vars.get("property_desc", ""),
            price_words=self.contract_vars.get("price_words", ""),
            price_num=self.contract_vars.get("price_num", ""),
            ownership_origin=self.contract_vars.get("ownership_origin", ""),
            # Carried through so AI-extracted clauses are not lost on every refresh.
            extra_foussoul=self.extra_foussoul,
            witness1_info=w1_data,
            witness2_info=w2_data,
            contract_vars=self.contract_vars
        )
        self.editor.setPlainText(base_text)
        self.ocr_edited_text = base_text

    def on_editor_text_changed(self):
        self.ocr_edited_text = self.editor.toPlainText()

    def quick_fill_witnesses(self):
        if hasattr(self, "var_witness1_name") and self.var_witness1_name:
            self.var_witness1_name.setText("حسان بن حمودة")
        if hasattr(self, "var_witness1_cin") and self.var_witness1_cin:
            self.var_witness1_cin.setText("08123456")
        if hasattr(self, "var_witness2_name") and self.var_witness2_name:
            self.var_witness2_name.setText("محمد العربي الزواوي")
        if hasattr(self, "var_witness2_cin") and self.var_witness2_cin:
            self.var_witness2_cin.setText("09876543")
        self.refresh_contract_preview_text()

    def copy_contract_text(self):
        app = QApplication.instance()
        if app:
            app.clipboard().setText(self.ocr_edited_text)
            QMessageBox.information(self, "Clipboard", "تم نسخ نص العقد الكامل إلى الحافظة بنجاح!")

    # ── Audio Actions ──
    def update_audio_party_toggle_ui(self):
        if not hasattr(self, "btn_audio_party_toggle"):
            return
        is_on = self.btn_audio_party_toggle.isChecked()
        if is_on:
            if self.lang == "fr":
                text = "🎙️ Extraction identité des parties depuis le vocal : ACTIVÉE"
            else:
                text = "🎙️ استخراج معطيات هويات الأطراف من الصوت : مفعّل (الاسم، الهوية، العنوان...)"
            style = """
                QPushButton {
                    background-color: #ecfdf5;
                    color: #047857;
                    border: 1.5px solid #10b981;
                    border-radius: 6px;
                    padding: 0 12px;
                    font-size: 12px;
                    font-weight: bold;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: #d1fae5;
                }
            """
        else:
            if self.lang == "fr":
                text = "🔇 Extraction identité des parties depuis le vocal : DÉSACTIVÉE (Focus foussoul & propriété)"
            else:
                text = "🔇 استخراج معطيات هويات الأطراف من الصوت : معطّل (فقط الفصول والملكية)"
            style = """
                QPushButton {
                    background-color: #f8fafc;
                    color: #475569;
                    border: 1.5px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 0 12px;
                    font-size: 12px;
                    font-weight: bold;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: #f1f5f9;
                    border-color: #94a3b8;
                }
            """
        self.btn_audio_party_toggle.setText(text)
        self.btn_audio_party_toggle.setStyleSheet(style)

    def start_recording(self):
        self.start_mic_btn.setEnabled(False)
        self.stop_mic_btn.setEnabled(True)
        self.delete_audio_btn.setVisible(False)
        self.delete_file_btn.setVisible(False)
        self.rec_seconds = 0
        self.mic_status_lbl.setText("🔴  جاري التسجيل الآن... [00:00]" if self.lang != "fr" else "🔴  Enregistrement en cours... [00:00]")
        self.mic_status_lbl.setStyleSheet("background-color: #fef2f2; color: #dc2626; font-size: 13px; font-weight: bold; border: 1px solid #fca5a5; border-radius: 6px; padding: 8px 12px;")
        self.rec_timer.start(1000)
        self.audio_recorder.start()

    def _update_rec_timer_display(self):
        self.rec_seconds += 1
        mins = self.rec_seconds // 60
        secs = self.rec_seconds % 60
        dot = "🔴" if self.rec_seconds % 2 == 0 else "⚪"
        msg = f"{dot}  جاري التسجيل الآن... [{mins:02d}:{secs:02d}]" if self.lang != "fr" else f"{dot}  Enregistrement en cours... [{mins:02d}:{secs:02d}]"
        self.mic_status_lbl.setText(msg)

    def on_recording_started(self):
        pass

    def on_recording_stopped(self, file_path):
        """Called only once the recorder has finished writing the file to disk."""
        if hasattr(self, "rec_timer") and self.rec_timer.isActive():
            self.rec_timer.stop()
        self.recorded_file_path = file_path
        self.start_mic_btn.setEnabled(True)
        self.stop_mic_btn.setEnabled(False)

        if not os.path.exists(file_path):
            self.audio_bytes = None
            self.mic_status_lbl.setText("لم يتم حفظ التسجيل")
            self.mic_status_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
            QMessageBox.warning(self, "Microphone", "تعذّر حفظ ملف التسجيل الصوتي. يرجى إعادة المحاولة.")
            return

        with open(file_path, "rb") as f:
            data = f.read()

        if len(data) < AudioRecorder.MIN_VALID_BYTES:
            self.audio_bytes = None
            self.mic_status_lbl.setText("التسجيل فارغ / Enregistrement vide")
            self.mic_status_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
            self.audio_path_lbl.setText("لا يوجد ملف")
            QMessageBox.warning(
                self, "Microphone",
                f"التسجيل الصوتي فارغ أو غير مكتمل ({len(data)} بايت).\n"
                "يرجى إعادة التسجيل والتحدث بوضوح قبل الضغط على «إيقاف»."
            )
            return

        level = self.audio_recorder.measure_level()
        if 0 <= level < AudioRecorder.SILENCE_RMS_THRESHOLD:
            self.audio_bytes = None
            self.mic_status_lbl.setText("لم يُلتقط أي صوت / Aucun son capté")
            self.mic_status_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
            self.audio_path_lbl.setText("لا يوجد ملف")
            QMessageBox.warning(
                self, "Microphone",
                f"لم يلتقط المايكروفون أي صوت مسموع (مستوى الإشارة {level:.0f}).\n\n"
                "يرجى التأكد من اختيار المايكروفون الصحيح والتحدث بوضوح، ثم إعادة التسجيل.\n\n"
                "تنبيه هام: إرسال تسجيل صامت للتفريغ قد يُنتج نصاً مُختلقاً لا يطابق الإملاء."
            )
            return

        self.audio_bytes = data
        self.audio_mime = getattr(self.audio_recorder, "output_mime", "audio/mp4")
        self.mic_status_lbl.setText(f"✅ تم تسجيل الصوت بنجاح ({len(data) // 1024} KB)")
        self.mic_status_lbl.setStyleSheet("background-color: #ecfdf5; color: #059669; font-weight: bold; border: 1px solid #6ee7b7; border-radius: 6px; padding: 8px 12px;")
        self.audio_path_lbl.setText(f"Enregistré : {Path(file_path).name}")
        self.save_audio_btn.setVisible(True)
        self.delete_audio_btn.setVisible(True)
        self.delete_file_btn.setVisible(True)

    def on_recording_error(self, err_msg):
        if hasattr(self, "rec_timer") and self.rec_timer.isActive():
            self.rec_timer.stop()
        self.start_mic_btn.setEnabled(True)
        self.stop_mic_btn.setEnabled(False)
        self.mic_status_lbl.setText("Erreur / خطأ في المايك")
        self.mic_status_lbl.setStyleSheet("color: #ef4444;")
        QMessageBox.warning(self, "Microphone", f"Erreur micro: {err_msg}")

    def stop_recording(self):
        if hasattr(self, "rec_timer") and self.rec_timer.isActive():
            self.rec_timer.stop()
        self.stop_mic_btn.setEnabled(False)
        self.mic_status_lbl.setText("⏳ جاري حفظ وتأكيد التسجيل... / Finalisation...")
        self.mic_status_lbl.setStyleSheet("background-color: #fffbeb; color: #d97706; font-weight: bold; border: 1px solid #fcd34d; border-radius: 6px; padding: 8px 12px;")
        self.audio_recorder.stop()

    def save_audio_to_laptop(self):
        if not self.audio_bytes:
            QMessageBox.warning(self, "حفظ التسجيل", "لا يوجد أي تسجيل صوتي لحفظه حالياً!")
            return

        ext = ".m4a"
        if self.audio_mime:
            if "wav" in self.audio_mime: ext = ".wav"
            elif "mp3" in self.audio_mime: ext = ".mp3"
            elif "ogg" in self.audio_mime: ext = ".ogg"

        default_name = f"تسجيل_توثيقي_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "حفظ التسجيل الصوتي على جهازك / Enregistrer le fichier audio",
            default_name,
            f"Audio Files (*{ext} *.mp3 *.wav *.m4a)"
        )

        if save_path:
            try:
                with open(save_path, "wb") as f:
                    f.write(self.audio_bytes)
                QMessageBox.information(
                    self,
                    "حفظ التسجيل",
                    f"تم حفظ التسجيل الصوتي بنجاح على جهازك:\n{save_path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "خطأ في الحفظ", f"تعذر حفظ الملف الصوتي: {e}")

    def clear_audio_recording(self):
        if hasattr(self, "rec_timer") and self.rec_timer.isActive():
            self.rec_timer.stop()
        self.audio_bytes = None
        self.recorded_file_path = ""
        self.audio_mime = "audio/wav"
        self.start_mic_btn.setEnabled(True)
        self.stop_mic_btn.setEnabled(False)
        self.mic_status_lbl.setText("حالة المايكروفون : جاهز (تم حذف التسجيل)")
        self.mic_status_lbl.setStyleSheet("color: #64748b; font-style: italic;")
        self.audio_path_lbl.setText("لا يوجد ملف")
        self.save_audio_btn.setVisible(False)
        self.delete_audio_btn.setVisible(False)
        self.delete_file_btn.setVisible(False)
        QMessageBox.information(self, "حذف التسجيل", "تم حذف التسجيل الصوتي بنجاح!")

    def upload_audio_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un fichier audio / اختيار تسجيل صوتي", "", "Audio (*.mp3 *.wav *.m4a *.ogg)"
        )
        if file_path:
            with open(file_path, "rb") as f:
                self.audio_bytes = f.read()
            ext = Path(file_path).suffix.lower()
            if "mp3" in ext: self.audio_mime = "audio/mp3"
            elif "m4a" in ext: self.audio_mime = "audio/m4a"
            elif "ogg" in ext: self.audio_mime = "audio/ogg"
            else: self.audio_mime = "audio/wav"
            self.audio_path_lbl.setText(Path(file_path).name)
            self.save_audio_btn.setVisible(True)
            self.delete_audio_btn.setVisible(True)
            self.delete_file_btn.setVisible(True)

    def reload_ai_engine(self):
        """
        Picks up the engine configured on the Settings page.

        Provider, model and keys are edited there now, so they are re-read before
        each generation rather than captured once when this page was built.
        """
        self.ocr_provider, self.ocr_model = config.load_ai_engine()
        self.ocr_api_key = config.load_saved_api_keys(self.ocr_provider)

    # ── Pipeline Generation Execution ──
    def run_unified_generation(self):
        # Read the current settings, in case they were changed since this page loaded.
        self.reload_ai_engine()

        if not self.ocr_api_key:
            QMessageBox.warning(
                self, "Configuration",
                "يرجى إدخال مفتاح API في صفحة «الإعدادات» ← «محرك الذكاء الاصطناعي» "
                "لتشغيل محرك صياغة العقود."
                if self.lang != "fr" else
                "Veuillez saisir une clé API dans Paramètres → Moteur d'Intelligence "
                "Artificielle pour activer la rédaction des contrats."
            )
            return

        # Refuse to "generate" from nothing. Without this the pipeline returns empty
        # party records and still reports success, producing a deed with no parties.
        has_p1 = any(p.get("client_id") or p.get("front_bytes") or p.get("back_bytes") for p in self.p1_parties)
        has_p2 = any(p.get("client_id") or p.get("front_bytes") or p.get("back_bytes") for p in self.p2_parties)
        audio_b = getattr(self, "audio_bytes", None)
        trans_out = getattr(self, "transcription_output", None)
        has_voice = bool(audio_b) or bool(trans_out.toPlainText().strip() if trans_out else False)

        if not (has_p1 or has_p2 or has_voice):
            QMessageBox.warning(
                self, "Génération",
                "يرجى اختيار حريف مسجل أو إرفاق بطاقات التعريف الوطنية قبل التوليد."
            )
            return

        p1_payload = []
        for p in self.p1_parties:
            p1_payload.append({
                "client_id": p["client_id"],
                "front_bytes": p["front_bytes"],
                "back_bytes": p["back_bytes"],
                "extracted": p.get("extracted"),
                "ocr_thread": p.get("ocr_thread"),
                "party_dict": p
            })
            
        p2_payload = []
        for p in self.p2_parties:
            p2_payload.append({
                "client_id": p["client_id"],
                "front_bytes": p["front_bytes"],
                "back_bytes": p["back_bytes"],
                "extracted": p.get("extracted"),
                "ocr_thread": p.get("ocr_thread"),
                "party_dict": p
            })

        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.generate_btn.setEnabled(False)

        proc_txt = self.procuration_input.toPlainText().strip() if hasattr(self, "procuration_input") and self.procuration_input else ""
        voice_txt = trans_out.toPlainText() if trans_out else ""
        include_audio_party = self.btn_audio_party_toggle.isChecked() if hasattr(self, "btn_audio_party_toggle") else False

        self.pipeline_thread = UnifiedPipelineThread(
            contract_type=self.selected_contract_type,
            p1_data=p1_payload,
            p2_data=p2_payload,
            procuration_text=proc_txt,
            audio_bytes=getattr(self, "audio_bytes", None),
            audio_mime=getattr(self, "audio_mime", "audio/wav"),
            voice_text=voice_txt,
            api_key=self.ocr_api_key,
            provider=self.ocr_provider,
            model=self.ocr_model,
            contract_vars=self.contract_vars,
            include_audio_party_info=include_audio_party
        )
        self.pipeline_thread.finished.connect(self.on_pipeline_finished)
        self.pipeline_thread.start()

    def on_pipeline_finished(self, res):
        self.progress_bar.setVisible(False)
        self.generate_btn.setEnabled(True)
        
        # Item 2: the step log goes to a panel in the interface, not to stdout, which
        # the --noconsole packaged build discards.
        self.render_pipeline_log(res)

        # Item 1: only a fatal crash aborts. A partial run (success=False, fatal=False)
        # still shows what was extracted, then reports exactly which steps failed.
        if res.get("fatal"):
            QMessageBox.critical(
                self, "Génération",
                f" توقفت المعالجة بسبب خطأ غير متوقع:\n\n{res.get('error')}\n\n"
                "لم يتم إنتاج أي عقد."
            )
            return


        ext_vars = res.get("extracted_vars", {})
        if ext_vars:
            party_keys = {
                "party1_name", "party1_cin", "party1_job", "party1_addr", "party1_cin_date", "party1_birthplace", "party1_birthdate",
                "party2_name", "party2_cin", "party2_job", "party2_addr", "party2_cin_date", "party2_birthplace", "party2_birthdate"
            }
            include_party = self.btn_audio_party_toggle.isChecked() if hasattr(self, "btn_audio_party_toggle") else False
            for k, v in ext_vars.items():
                if v:
                    if not include_party and k in party_keys:
                        continue
                    self.contract_vars[k] = v
                    
        p1_list = res.get("party1_list", [])
        if p1_list and p1_list[0].get("full_name"):
            c = p1_list[0]
            if c.get("full_name"): self.contract_vars["party1_name"] = c.get("full_name")
            if c.get("cin_number"): self.contract_vars["party1_cin"] = c.get("cin_number")
            if c.get("job"): self.contract_vars["party1_job"] = c.get("job")
            if c.get("address"): self.contract_vars["party1_addr"] = c.get("address")
            if c.get("issue_date"): self.contract_vars["party1_cin_date"] = c.get("issue_date")
            if c.get("birth_place"): self.contract_vars["party1_birthplace"] = c.get("birth_place")
            if c.get("birth_date"): self.contract_vars["party1_birthdate"] = c.get("birth_date")

        p2_list = res.get("party2_list", [])
        if p2_list and p2_list[0].get("full_name"):
            c = p2_list[0]
            if c.get("full_name"): self.contract_vars["party2_name"] = c.get("full_name")
            if c.get("cin_number"): self.contract_vars["party2_cin"] = c.get("cin_number")
            if c.get("job"): self.contract_vars["party2_job"] = c.get("job")
            if c.get("address"): self.contract_vars["party2_addr"] = c.get("address")
            if c.get("issue_date"): self.contract_vars["party2_cin_date"] = c.get("issue_date")
            if c.get("birth_place"): self.contract_vars["party2_birthplace"] = c.get("birth_place")
            if c.get("birth_date"): self.contract_vars["party2_birthdate"] = c.get("birth_date")

        # Keep the complete records so a later refresh rebuilds from real data.
        self.p1_extracted = p1_list
        self.p2_extracted = p2_list
        self.extra_foussoul = res.get("extra_foussoul") or []

        self.update_ui_fields_from_state()
        self.refresh_chosen_clients_archive_list()

        if res.get("spoken_content"):
            if hasattr(self, "transcription_output") and self.transcription_output:
                self.transcription_output.setPlainText(res.get("spoken_content"))
            if hasattr(self, "audio_tabs") and self.audio_tabs:
                self.audio_tabs.setCurrentIndex(2)

        try:
            self.refresh_contract_preview_text()
        except Exception as ex_build:
            QMessageBox.critical(
                self, "Génération",
                "تعذّر تجميع نص العقد من المعطيات المستخرجة.\n"
                f"التفاصيل: {ex_build}\n\n"
                "لم يتم إنتاج عقد. يرجى مراجعة المعطيات وإعادة المحاولة."
            )
            return

        self._report_pipeline_outcome(res)

    def render_pipeline_log(self, res):
        """
        Renders every pipeline step into the in-app log panel.

        Replaces print(), which produced nothing at all in the --noconsole build and
        was the direct cause of failures being invisible to the notary.
        """
        lines = []
        for log in res.get("logs", []):
            text = str(log)
            if text.startswith("") or "تنبيه" in text:
                colour = "#fbbf24"
            elif text.startswith(""):
                colour = "#f87171"
            elif text.startswith(""):
                colour = "#4ade80"
            else:
                colour = "#e2e8f0"
            lines.append(f'<div style="color:{colour}; margin-bottom:3px;">{html.escape(text)}</div>')

        if res.get("fatal"):
            verdict = '<div style="color:#f87171; font-weight:bold; margin-top:6px;"> فشلت المعالجة كلياً.</div>'
        elif not res.get("success"):
            verdict = ('<div style="color:#fbbf24; font-weight:bold; margin-top:6px;">'
                       'اكتملت المعالجة مع أخطاء — العقد غير مكتمل.</div>')
        else:
            verdict = ('<div style="color:#4ade80; font-weight:bold; margin-top:6px;">'
                       'تمت كل الخطوات بنجاح.</div>')

        self.log_view.setHtml("".join(lines) + verdict)
        self.log_panel.setVisible(False)

    def _report_pipeline_outcome(self, res):
        """
        Tells the notary what actually happened.

        A deed is produced even when a card could not be read, so silence here would
        mean signing an incomplete act believing it complete. Warnings are shown in
        the interface, not printed to a console the packaged app does not have.
        """
        warnings = res.get("warnings") or []
        cards_attempted = res.get("cards_attempted", 0)
        cards_read = res.get("cards_read", 0)
        audio_attempted = res.get("audio_attempted", False)
        audio_ok = res.get("audio_ok", False)

        if not warnings:
            QMessageBox.information(self, "Génération", "تم توليد وتجميع العقد الرسمي بنجاح!")
            return

        summary_lines = []
        if cards_attempted:
            summary_lines.append(f"• بطاقات التعريف: تمت قراءة {cards_read} من {cards_attempted}.")
        if audio_attempted:
            summary_lines.append(f"• التفريغ الصوتي: {'نجح' if audio_ok else 'لم ينجح'}.")

        detail = "\n".join(f" {w}" for w in warnings[:8])
        if len(warnings) > 8:
            detail += f"\n… و{len(warnings) - 8} تنبيهات أخرى."

        everything_failed = (cards_attempted and cards_read == 0) and (not audio_attempted or not audio_ok)

        if everything_failed:
            QMessageBox.critical(
                self, "Génération",
                "لم يتم استخراج أي معطيات: فشلت كل خطوات المعالجة.\n\n"
                + "\n".join(summary_lines) + "\n\n" + detail +
                "\n\nالعقد المعروض غير مكتمل — يرجى معالجة الأسباب أعلاه وإعادة التوليد قبل الاعتماد عليه."
            )
        else:
            QMessageBox.warning(
                self, "Génération",
                "تم توليد العقد لكن بعض الخطوات لم تكتمل.\n\n"
                + "\n".join(summary_lines) + "\n\n" + detail +
                "\n\nيرجى مراجعة الحقول الناقصة يدوياً قبل اعتماد العقد."
            )

    def reset_pipeline(self):
        self.contract_vars = contract_templates.get_default_variables(self.selected_contract_type)
        self.update_ui_fields_from_state()
        self.editor.clear()
        if hasattr(self, "procuration_input") and self.procuration_input:
            self.procuration_input.clear()
        if hasattr(self, "transcription_output") and self.transcription_output:
            self.transcription_output.clear()
        self.audio_bytes = None
        if hasattr(self, "audio_path_lbl") and self.audio_path_lbl:
            self.audio_path_lbl.setText("لا يوجد ملف")
        self.p1_parties = [{"client_id": "", "front_bytes": None, "back_bytes": None, "front_lbl": "لا يوجد", "back_lbl": "لا يوجد"}]
        self.p2_parties = [{"client_id": "", "front_bytes": None, "back_bytes": None, "front_lbl": "لا يوجد", "back_lbl": "لا يوجد"}]

        # Clear extracted records too, so a reset cannot leak the previous act's data.
        self.p1_extracted = []
        self.p2_extracted = []
        self.extra_foussoul = []

        for i in range(self.archive_list.count()):
            item = self.archive_list.item(i)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
            
        self.rebuild_parties_ui()
        if hasattr(self, "audit_lay") and self.audit_lay:
            self.clear_layout(self.audit_lay)
            self.audit_status_lbl = QLabel(("Aucune vérification effectuée" if self.lang == "fr" else "لم يتم فحص العقد بعد"), getattr(self, "audit_container", None))
            self.audit_status_lbl.setStyleSheet("color: #64748b; font-style: italic;")
            self.audit_lay.addWidget(self.audit_status_lbl)
        
        self.refresh_contract_preview_text()

    # ── Audit conformité style severity render ──
    def run_legal_audit(self):
        self.clear_layout(self.audit_lay)
        self.pull_state_from_ui_fields()
        res = notary_checker.audit_notary_contract(self.ocr_edited_text, self.contract_vars, self.selected_contract_type)
        self.audit_result = res
        
        score = res.get("score", 100)
        
        score_card = QFrame()
        score_card_lay = QHBoxLayout(score_card)
        score_card_lay.setContentsMargins(6, 6, 6, 6)
        
        score_lbl = QLabel(f"<b>مؤشر الأمان التوثيقي: {score}%</b>")
        score_card_lay.addWidget(score_lbl)
        
        if score >= 90:
            score_card.setStyleSheet("background: #ecfdf5; border: 1.5px solid #10b981; border-radius: 6px; color: #065f46;")
        elif score >= 70:
            score_card.setStyleSheet("background: #fffbeb; border: 1.5px solid #f59e0b; border-radius: 6px; color: #78350f;")
        else:
            score_card.setStyleSheet("background: #fef2f2; border: 1.5px solid #ef4444; border-radius: 6px; color: #7f1d1d;")
            
        self.audit_lay.addWidget(score_card)
        
        anom_list = res.get("anomalies", [])
        if not anom_list:
            clean_lbl = QLabel("لا توجد أي ثغرات قانونية مكتشفة بالعقد.")
            clean_lbl.setStyleSheet("color: #059669; font-weight: bold;")
            self.audit_lay.addWidget(clean_lbl)
        else:
            for a in anom_list:
                a_type = a.get("type", "INFO")
                a_title = a.get("title", "")
                a_details = a.get("details", "")
                a_sugg = a.get("suggestion", "")
                
                card = QFrame()
                card_lay = QVBoxLayout(card)
                card_lay.setContentsMargins(8, 8, 8, 8)
                card_lay.setSpacing(4)
                
                title_lbl = QLabel(f"<b>[{a_type}] {a_title}</b>")
                details_lbl = QLabel(a_details)
                details_lbl.setWordWrap(True)
                sugg_lbl = QLabel(f" التوصية: {a_sugg}")
                sugg_lbl.setWordWrap(True)
                sugg_lbl.setStyleSheet("font-style: italic;")
                
                card_lay.addWidget(title_lbl)
                card_lay.addWidget(details_lbl)
                card_lay.addWidget(sugg_lbl)
                
                if a_type == "CRITICAL":
                    card.setStyleSheet("background: #fef2f2; border: 1px solid #f87171; border-radius: 6px; color: #991b1b;")
                elif a_type == "WARNING":
                    card.setStyleSheet("background: #fffbeb; border: 1px solid #fbbf24; border-radius: 6px; color: #92400e;")
                else:
                    card.setStyleSheet("background: #f0f9ff; border: 1px solid #38bdf8; border-radius: 6px; color: #075985;")
                    
                self.audit_lay.addWidget(card)

    # ── Export & Archiving actions ──
    # Minimum plausible length for a Tunisian notarial deed. Anything shorter means
    # nothing was generated yet, and must not be exported or filed as a client's act.
    MIN_CONTRACT_CHARS = 200

    # Les informations sans lesquelles un acte notarie n'en est pas un : chaque
    # partie doit avoir un nom et un numero de carte d'identite.
    CHAMPS_OBLIGATOIRES = (
        ("party1_name", "اسم"),
        ("party1_cin", "رقم بطاقة تعريف"),
        ("party2_name", "اسم"),
        ("party2_cin", "رقم بطاقة تعريف"),
    )

    def _champs_obligatoires_manquants(self):
        """Les informations obligatoires absentes, nommées en arabe."""
        try:
            import contract_templates
            roles = contract_templates.get_party_role_names(self.selected_contract_type)
            role1, role2 = roles[0], roles[2]
        except Exception:
            role1, role2 = "الطرف الأول", "الطرف الثاني"

        c_type = self.selected_contract_type or ""
        is_single_party = any(w in c_type for w in ["فريضة", "وفاة", "حوز", "توكيل", "إسقاط", "وصل", "توصية", "إشهار", "تكليف"])

        manquants = []
        for cle, libelle in self.CHAMPS_OBLIGATOIRES:
            if is_single_party and cle.startswith("party2"):
                continue
            if (self.contract_vars.get(cle) or "").strip():
                continue
            role = role1 if cle.startswith("party1") else role2
            manquants.append(f"{libelle} {role}")
        return manquants

    def _contract_ready_for_output(self, action_label: str) -> bool:
        """Blocks export/archiving of an empty or stub contract, which used to succeed silently."""
        text = (self.ocr_edited_text or "").strip()

        if not text:
            QMessageBox.warning(
                self, "المستند",
                f"لا يوجد نص عقد لـ{action_label}.\n"
                "يرجى الضغط على «رقمنة» أولاً لتوليد العقد."
            )
            return False

        if len(text) < self.MIN_CONTRACT_CHARS:
            QMessageBox.warning(
                self, "المستند",
                f"نص العقد غير مكتمل ({len(text)} حرفاً فقط) — لا يمكن {action_label}.\n"
                "يرجى إتمام صياغة العقد قبل الحفظ."
            )
            return False

        # A deed with no identified party is not a deed. On ne se contente plus
        # de le signaler quand TOUTES les parties manquent : on enumere chaque
        # information absente, sous son nom juridique, pour que le notaire
        # sache exactement quoi completer.
        manquants = self._champs_obligatoires_manquants()
        if manquants:
            liste = "\n".join(f"    • {m}" for m in manquants)
            proceed = QMessageBox.question(
                self, "معطيات ناقصة",
                f"تنقص العقد معطيات إجبارية ({len(manquants)}) :\n\n{liste}\n\n"
                f"يمكنك إتمامها في قسم « الحقول التحريرية » ثم إعادة المحاولة.\n\n"
                f"هل تريد المتابعة رغم ذلك؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return False

        return True

    def export_word(self):
        if not self._contract_ready_for_output("التصدير بصيغة Word"):
            return
        selected_dossier_id = self.dossier_combo.currentData() if hasattr(self, "dossier_combo") else ""
        custom_dossier_input = self.var_dossier_num.text().strip() if hasattr(self, "var_dossier_num") else ""
        dossier_num = selected_dossier_id or custom_dossier_input
        default_filename = f"ملف_رقم_{dossier_num}.docx" if dossier_num else f"{self.selected_contract_type}_{datetime.date.today()}.docx"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter en Word / حفظ بصيغة Word",
            default_filename,
            "Word Documents (*.docx)"
        )
        if save_path:
            try:
                docx_bytes = pdf_generator.generate_docx_from_transcription(
                    title=f"{self.selected_contract_type} — {office_profile.office_title()}",
                    text=self.ocr_edited_text,
                    metadata={
                        "تاريخ التحرير": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "عدل الإشهاد": office_profile.display_name(),
                        "نوع المحرر": self.selected_contract_type
                    }
                )
                with open(save_path, "wb") as f:
                    f.write(docx_bytes)
                QMessageBox.information(self, "Export", "تم تصدير وحفظ مستند Word بنجاح!")
            except Exception as e:
                QMessageBox.warning(self, "Export", f"فشل التصدير: {str(e)}")

    def export_pdf(self):
        if not self._contract_ready_for_output("التصدير بصيغة PDF"):
            return
        selected_dossier_id = self.dossier_combo.currentData() if hasattr(self, "dossier_combo") else ""
        custom_dossier_input = self.var_dossier_num.text().strip() if hasattr(self, "var_dossier_num") else ""
        dossier_num = selected_dossier_id or custom_dossier_input
        default_filename = f"ملف_رقم_{dossier_num}.pdf" if dossier_num else f"{self.selected_contract_type}_{datetime.date.today()}.pdf"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter en PDF / حفظ بصيغة PDF",
            default_filename,
            "PDF Documents (*.pdf)"
        )
        if save_path:
            try:
                pdf_bytes = pdf_generator.generate_pdf_from_transcription(
                    title=f"{self.selected_contract_type} — {office_profile.office_title()}",
                    text=self.ocr_edited_text
                )
                with open(save_path, "wb") as f:
                    f.write(pdf_bytes)
                QMessageBox.information(self, "Export", "تم تصدير وحفظ مستند PDF بنجاح!")
            except Exception as e:
                QMessageBox.warning(self, "Export", f"فشل التصدير: {str(e)}")

    # ── Multiple Archiving ──
    def open_case_creation_popup(self, p1_names_list, p2_names_list, selected_client_ids):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QTextEdit, QMessageBox, QDialogButtonBox, QFileDialog
        from ui.pages.fiche_client_page import MoneySpinBox

        is_fr = self.lang == "fr"
        dialog = QDialog(self)
        dialog.setWindowTitle("Nouveau Dossier Notarié" if is_fr else "فتح ملف إشهاد جديد")
        dialog.setMinimumWidth(560)
        dialog.setModal(True)
        lay = QVBoxLayout(dialog)
        lay.setSpacing(10)

        # N° dossier custom
        row_num = QHBoxLayout()
        row_num.addWidget(QLabel("رقم الملف (اختياري) :" if not is_fr else "N° Dossier (optionnel) :"))
        num_input = QLineEdit()
        custom_input = self.var_dossier_num.text().strip() if hasattr(self, "var_dossier_num") else ""
        if custom_input:
            num_input.setText(custom_input)
        row_num.addWidget(num_input, stretch=1)
        lay.addLayout(row_num)

        # Contract type (Categorized Options from contract_templates)
        type_lbl = QLabel("نوع العقد :" if not is_fr else "Type de contrat :")
        type_combo = QComboBox()
        import contract_templates
        contract_templates.populate_categorized_contract_types(type_combo, default_selected=self.selected_contract_type)
        lay.addWidget(type_lbl)
        lay.addWidget(type_combo)

        p1_str = "\n".join([n for n in p1_names_list if n])
        p2_str = "\n".join([n for n in p2_names_list if n])
        all_party_names = [n for n in (p1_names_list + p2_names_list) if n]
        names_str = " & ".join(all_party_names)

        # Notes / Description
        desc_lbl = QLabel("ملاحظات العقد :" if not is_fr else "Notes du contrat :")
        desc_input = QTextEdit()
        desc_input.setMaximumHeight(70)
        default_desc = f"الأطراف المربوطة بالعقد:\nالطرف الأول: {', '.join(p1_names_list)}\nالطرف الثاني: {', '.join(p2_names_list)}" if (p1_names_list or p2_names_list) else ""
        desc_input.setPlainText(default_desc)
        lay.addWidget(desc_lbl)
        lay.addWidget(desc_input)

        # Financial section
        fin_sep = QLabel("معطيات الخلاص والمالية" if not is_fr else "Informations Financières")
        fin_sep.setStyleSheet("font-weight:bold; color:#0284c7; margin-top:6px;")
        lay.addWidget(fin_sep)

        fin_row = QHBoxLayout()
        fin_row.addWidget(QLabel("الإجمالي :" if not is_fr else "Total :"))
        tot_spin = MoneySpinBox(dialog)
        fin_row.addWidget(tot_spin)
        fin_row.addWidget(QLabel("التسبقة :" if not is_fr else "Acompte :"))
        av_spin = MoneySpinBox(dialog)
        fin_row.addWidget(av_spin)
        lay.addLayout(fin_row)

        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel("طريقة الخلاص :" if not is_fr else "Mode de règlement :"))
        notes_input = QLineEdit()
        notes_row.addWidget(notes_input, stretch=1)
        lay.addLayout(notes_row)

        # File attachments
        files_sep = QLabel("وثائق الملف" if not is_fr else "Documents du dossier")
        files_sep.setStyleSheet("font-weight:bold; margin-top:6px;")
        lay.addWidget(files_sep)

        new_case_files = []
        files_count_lbl = QLabel("لا يوجد ملف محدد" if not is_fr else "Aucun fichier")
        files_count_lbl.setStyleSheet("color:#64748b; font-style:italic; font-size:11px;")

        def browse_attach():
            paths, _ = QFileDialog.getOpenFileNames(
                dialog, "اختيار ملفات / Fichiers", "",
                "Fichiers (*.pdf *.docx *.doc *.jpg *.jpeg *.png)"
            )
            if paths:
                new_case_files.clear()
                new_case_files.extend(paths)
                files_count_lbl.setText(f"{len(paths)} ملف / fichier(s) sélectionné(s)")

        files_row = QHBoxLayout()
        browse_f_btn = QPushButton("استعراض" if not is_fr else "Parcourir")
        browse_f_btn.clicked.connect(browse_attach)
        files_row.addWidget(browse_f_btn)
        files_row.addWidget(files_count_lbl, stretch=1)
        lay.addLayout(files_row)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        lay.addWidget(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            tot_v = tot_spin.value()
            av_v = av_spin.value()
            if av_v >= tot_v and tot_v > 0:
                p_status = "خالص بالكامل"
            elif av_v > 0:
                p_status = "تسبقة"
            else:
                p_status = "غير خالص"

            primary_cid = selected_client_ids[0] if selected_client_ids else ""
            custom_id = num_input.text().strip() or None
            case_title = f"{type_combo.currentText()} ({names_str})" if names_str else f"{type_combo.currentText()}"

            new_id = reception.create_case(
                client_id=primary_cid,
                service_type=type_combo.currentText(),
                title=case_title,
                description=desc_input.toPlainText().strip(),
                total_amount=tot_v,
                avance_amount=av_v,
                payment_status=p_status,
                payment_notes=notes_input.text().strip(),
                custom_case_id=custom_id,
                party1_name=p1_str,
                party2_name=p2_str,
                client_ids=selected_client_ids
            )

            # Save attached files to ALL client folders
            for fpath in new_case_files:
                try:
                    with open(fpath, 'rb') as f:
                        fbytes = f.read()
                    for cid in selected_client_ids:
                        reception.save_client_document(cid, fbytes, f"Dossier_{new_id}_{Path(fpath).name}")
                except Exception:
                    pass

            return new_id
        return None

    def archive_to_clients(self):
        if not self._contract_ready_for_output("الأرشفة"):
            return

        selected_client_ids = []
        selected_client_names = []

        for i in range(self.archive_list.count()):
            item = self.archive_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                cid = item.data(Qt.ItemDataRole.UserRole)
                if cid and cid not in selected_client_ids:
                    selected_client_ids.append(cid)
                    selected_client_names.append(item.text())

        if not selected_client_ids and self.archive_list.count() > 0:
            for i in range(self.archive_list.count()):
                item = self.archive_list.item(i)
                if item:
                    item.setCheckState(Qt.CheckState.Checked)
                    cid = item.data(Qt.ItemDataRole.UserRole)
                    if cid and cid not in selected_client_ids:
                        selected_client_ids.append(cid)
                        selected_client_names.append(item.text())

        if not selected_client_ids:
            for p in self.p1_parties + self.p2_parties:
                cid = p.get("client_id")
                if cid and cid not in selected_client_ids:
                    selected_client_ids.append(cid)

        if not selected_client_ids:
            QMessageBox.warning(self, "Archivage", "يرجى تحديد حريف واحد على الأقل من القائمة لتأمين حفظ العقد بملفهم.")
            return

        try:
            selected_dossier_id = self.dossier_combo.currentData() if hasattr(self, "dossier_combo") else ""

            p1_names_list = [p.get("full_name", "").strip() for p in getattr(self, "p1_extracted", []) if p.get("full_name")]
            p2_names_list = [p.get("full_name", "").strip() for p in getattr(self, "p2_extracted", []) if p.get("full_name")]

            if not p1_names_list and self.contract_vars.get("party1_name"):
                p1_names_list = [self.contract_vars.get("party1_name").strip()]
            if not p2_names_list and self.contract_vars.get("party2_name"):
                p2_names_list = [self.contract_vars.get("party2_name").strip()]

            target_case_id = selected_dossier_id

            if not target_case_id:
                # Trigger the official "Nouveau Dossier Notarié" popup dialog
                target_case_id = self.open_case_creation_popup(p1_names_list, p2_names_list, selected_client_ids)
                if not target_case_id:
                    return

            docx_bytes = pdf_generator.generate_docx_from_transcription(
                title=f"{self.selected_contract_type} — {office_profile.office_title()}",
                text=self.ocr_edited_text,
                metadata={
                    "تاريخ التحرير": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "عدل الإشهاد": office_profile.display_name(),
                    "نوع المحرر": self.selected_contract_type
                }
            )
            pdf_bytes = pdf_generator.generate_pdf_from_transcription(
                title=f"{self.selected_contract_type} — {office_profile.office_title()}",
                text=self.ocr_edited_text
            )
            
            reception.link_clients_to_case(target_case_id, selected_client_ids)

            saved_count = 0
            fn_docx = f"ملف_رقم_{target_case_id}.docx"
            fn_pdf = f"ملف_رقم_{target_case_id}.pdf"

            for cid in selected_client_ids:
                reception.save_client_document(cid, docx_bytes, fn_docx)
                reception.save_client_document(cid, pdf_bytes, fn_pdf)
                saved_count += 1

            self.update_dossiers_combo()
            idx = self.dossier_combo.findData(target_case_id)
            if idx >= 0:
                self.dossier_combo.setCurrentIndex(idx)

            QMessageBox.information(
                self, "Archivage", 
                f"تم أرشفة وحفظ العقد بنجاح والمربوط بالملف رقم {target_case_id} في مجلدات الحرفاء المحددين (عدد الحرفاء المربوطين: {saved_count})!"
            )
            
            for i in range(self.archive_list.count()):
                item = self.archive_list.item(i)
                if item:
                    item.setCheckState(Qt.CheckState.Unchecked)
                
        except Exception as e:
            QMessageBox.warning(self, "Archivage", f"حدث خطأ أثناء أرشفة المستند: {str(e)}")

    def update_language(self, lang_code):
        self.lang = lang_code
        if lang_code == "ar":
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        # Retranslate the contract-variables form. These labels used to be built as
        # anonymous QLabels with both languages baked into one string, so switching
        # language left them showing "Nom / الاسم" forever.
        is_fr = lang_code == "fr"
        for lb, fr, ar, bold in getattr(self, "var_labels", {}).values():
            text = fr if is_fr else ar
            lb.setText(f"<b>{text}</b>" if bold else text)

        if hasattr(self, "lbl_type"):
            self.lbl_type.setText("Type de contrat :" if is_fr else "نوع العقد :")
        if hasattr(self, "quick_witness_btn"):
            self.quick_witness_btn.setText(
                "Remplir les témoins" if is_fr else "تعبئة الشهود")
        if hasattr(self, "sec_vars"):
            self.sec_vars.title_lbl.setText(
                "3. Variables du contrat" if is_fr
                else "3. الحقول التحريرية والتفاصيل المادية للعقد")

    def open_scanner_settings_dialog(self):
        dlg = ScannerSettingsDialog(self)
        dlg.exec()

    def open_farida_calculator(self):
        from ui.components.farida_dialog import TunisianFaridaDialog
        selected_cid = None
        if hasattr(self, "selected_p1") and self.selected_p1:
            selected_cid = self.selected_p1.get("client_id")

        dlg = TunisianFaridaDialog(self, lang=self.lang, client_id=selected_cid)
        if hasattr(dlg, "farida_inserted"):
            dlg.farida_inserted.connect(self._on_farida_inserted)
        dlg.generate_partition_requested.connect(self._on_generate_partition_from_farida)
        dlg.exec()

    def _on_farida_inserted(self, farida_result: dict):
        """1-Click Direct Auto-Insert of Farida into contract editor and variables."""
        legal_text = farida_result.get("legal_notarial_text", "")
        if not legal_text:
            return

        c_type = farida_result.get("contract_type", "فريضة شرعية")
        # 1. Switch contract type to matching farida type
        self.select_contract_type(c_type)

        # 2. Update contract variables state
        self.contract_vars["ownership_origin"] = legal_text
        if hasattr(self, "var_ownership_origin"):
            self.var_ownership_origin.setPlainText(legal_text)

        # 3. Direct insertion into the Main Contract Editor widget
        if hasattr(self, "editor") and self.editor:
            self.editor.setPlainText(legal_text)
            self.ocr_edited_text = legal_text

    def _on_generate_partition_from_farida(self, farida_result: dict):
        """Auto-generates Amicable Partition Contract (عقد مقاسمة)."""
        self.select_contract_type("عقد مقاسمة")
        self._on_farida_inserted(farida_result)
