import office_profile
import os
import html
import datetime
import time
from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton, QTabWidget, QFrame, QFileDialog, QMessageBox, QProgressBar, QListWidget, QListWidgetItem, QGridLayout, QScrollArea, QMenu
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
    
    def __init__(self, contract_type, p1_data, p2_data, procuration_text, audio_bytes, audio_mime, voice_text, api_key, provider, model, contract_vars):
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
                                "cin_number": sc.get("cin_number", ""),
                                "issue_date": sc.get("cin_date_place", ""),
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
                    # Always merge any missing fields (e.g. dictated Job or Address) from audio dictation
                    if results.get("extracted_vars"):
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
                                "cin_number": sc.get("cin_number", ""),
                                "issue_date": sc.get("cin_date_place", ""),
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

                    # Always merge any missing fields (e.g. dictated Job or Address) from audio dictation
                    if results.get("extracted_vars"):
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
        self.type_btn = QPushButton(left_panel)
        self.type_btn.setFixedHeight(36)
        self.type_btn.setMinimumWidth(320)
        self.type_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.type_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 14px;
                font-size: 13px;
                font-weight: bold;
                text-align: right;
            }
            QPushButton:hover {
                background-color: #f8fafc;
                border-color: #3b82f6;
            }
        """)

        self.lbl_type = QLabel("Type de contrat :" if self.lang == "fr" else "نوع العقد :", left_panel)
        self.lbl_type.setStyleSheet("font-size:13px; font-weight:700; color:#1e293b; border:none;")

        self.btn_farida = QPushButton("حاسبة الفريضة" if self.lang == "ar" else "Calculateur d'Héritage", left_panel)
        self.btn_farida.setFixedHeight(36)
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

        selectors_box.addWidget(self.lbl_type)
        selectors_box.addWidget(self.type_btn, 1)
        selectors_box.addWidget(self.btn_farida)
        left_lay.addLayout(selectors_box)

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

        # ── Collapsible Section 2: Voice Audio Dictation (3 tabs inside) ──
        self.sec_audio = CollapsibleSection(("2. Dictée vocale des clauses du contrat" if self.lang == "fr" else "2. التسجيل والإملاء الصوتي لفصول العقد"), expanded=False, parent=left_panel)
        self.audio_tabs = QTabWidget()
        
        # Tab 1: Mic
        self.sub_tab_mic = QWidget()
        mic_lay = QVBoxLayout(self.sub_tab_mic)
        mic_btn_lay = QHBoxLayout()
        self.start_mic_btn = QPushButton("Enregistrer" if self.lang == "fr" else "🎙️ بدء التسجيل", self.sub_tab_mic)
        self.start_mic_btn.setProperty("class", "PrimaryButton")
        self.start_mic_btn.clicked.connect(self.start_recording)

        self.stop_mic_btn = QPushButton("Arrêter" if self.lang == "fr" else "⏹️ إيقاف التسجيل", self.sub_tab_mic)
        self.stop_mic_btn.setProperty("class", "SecondaryButton")
        self.stop_mic_btn.setEnabled(False)
        self.stop_mic_btn.clicked.connect(self.stop_recording)

        self.save_audio_btn = QPushButton("Sauvegarder" if self.lang == "fr" else "💾 حفظ التسجيل", self.sub_tab_mic)
        self.save_audio_btn.setStyleSheet("background-color: #eff6ff; color: #1d4ed8; border: 1px solid #93c5fd; font-weight: bold; border-radius: 6px; padding: 6px 14px;")
        self.save_audio_btn.setVisible(False)
        self.save_audio_btn.clicked.connect(self.save_audio_to_laptop)

        self.delete_audio_btn = QPushButton("Supprimer" if self.lang == "fr" else "🗑️ حذف التسجيل", self.sub_tab_mic)
        self.delete_audio_btn.setStyleSheet("background-color: #fee2e2; color: #dc2626; border: 1px solid #fca5a5; font-weight: bold; border-radius: 6px; padding: 6px 14px;")
        self.delete_audio_btn.setVisible(False)
        self.delete_audio_btn.clicked.connect(self.clear_audio_recording)

        mic_btn_lay.addWidget(self.start_mic_btn)
        mic_btn_lay.addWidget(self.stop_mic_btn)
        mic_btn_lay.addWidget(self.save_audio_btn)
        mic_btn_lay.addWidget(self.delete_audio_btn)
        mic_lay.addLayout(mic_btn_lay)
        self.mic_status_lbl = QLabel(("Statut : prêt" if self.lang == "fr" else "حالة المايكروفون : جاهز"), self.sub_tab_mic)
        self.mic_status_lbl.setStyleSheet("color: #64748b; font-style: italic;")
        mic_lay.addWidget(self.mic_status_lbl)
        self.audio_tabs.addTab(self.sub_tab_mic, "تسجيل مايكروفون")
        
        # Tab 2: File Import
        self.sub_tab_file = QWidget()
        file_lay = QVBoxLayout(self.sub_tab_file)
        file_btn_lay = QHBoxLayout()
        self.upload_audio_btn = QPushButton(("Choisir un fichier audio" if self.lang == "fr" else "📁 اختيار ملف صوتي"), self.sub_tab_file)
        self.upload_audio_btn.setProperty("class", "SecondaryButton")
        self.upload_audio_btn.clicked.connect(self.upload_audio_file)

        self.delete_file_btn = QPushButton(("Supprimer" if self.lang == "fr" else "🗑️ حذف الملف"), self.sub_tab_file)
        self.delete_file_btn.setStyleSheet("background-color: #fee2e2; color: #dc2626; border: 1px solid #fca5a5; font-weight: bold; border-radius: 6px; padding: 6px 14px;")
        self.delete_file_btn.setVisible(False)
        self.delete_file_btn.clicked.connect(self.clear_audio_recording)

        file_btn_lay.addWidget(self.upload_audio_btn)
        file_btn_lay.addWidget(self.delete_file_btn)
        file_lay.addLayout(file_btn_lay)
        self.audio_path_lbl = QLabel(("Aucun fichier" if self.lang == "fr" else "لا يوجد ملف"), self.sub_tab_file)
        file_lay.addWidget(self.audio_path_lbl)
        self.audio_tabs.addTab(self.sub_tab_file, "استيراد ملف صوتي")
        
        # Tab 3: Text Direct Input
        self.sub_tab_text = QWidget()
        text_lay = QVBoxLayout(self.sub_tab_text)
        self.transcription_output = QTextEdit(self.sub_tab_text)
        text_lay.addWidget(self.transcription_output)
        self.audio_tabs.addTab(self.sub_tab_text, "إملاء وكتابة مباشرة")
        
        self.sec_audio.add_widget(self.audio_tabs)
        left_lay.addWidget(self.sec_audio)

        # ── Collapsible Section 3: Variables Form ──
        self.sec_vars = CollapsibleSection(
            "3. Variables du contrat" if self.lang == "fr"
            else "3. الحقول التحريرية والتفاصيل المادية للعقد",
            expanded=False, parent=left_panel)
        vars_grid = QGridLayout()
        vars_grid.setSpacing(8)
        
        self.var_p1_name = QLineEdit(self.sec_vars)
        self.var_p1_cin = QLineEdit(self.sec_vars)
        self.var_p1_job = QLineEdit(self.sec_vars)
        self.var_p1_addr = QLineEdit(self.sec_vars)
        
        self.var_p2_name = QLineEdit(self.sec_vars)
        self.var_p2_cin = QLineEdit(self.sec_vars)
        self.var_p2_job = QLineEdit(self.sec_vars)
        self.var_p2_addr = QLineEdit(self.sec_vars)
        
        self.var_property_desc = QTextEdit(self.sec_vars)
        self.var_property_desc.setMaximumHeight(50)
        self.var_ownership_origin = QTextEdit(self.sec_vars)
        self.var_ownership_origin.setMaximumHeight(50)
        self.var_price_num = QLineEdit(self.sec_vars)
        self.var_price_words = QLineEdit(self.sec_vars)
        
        self.var_prop_title = QLineEdit(self.sec_vars)
        self.var_titre_foncier = QLineEdit(self.sec_vars)
        self.var_titre_gov = QLineEdit(self.sec_vars)
        self.var_prop_location = QLineEdit(self.sec_vars)
        self.var_prop_area = QLineEdit(self.sec_vars)
        
        self.var_witness1_name = QLineEdit(self.sec_vars)
        self.var_witness1_cin = QLineEdit(self.sec_vars)
        self.var_witness2_name = QLineEdit(self.sec_vars)
        self.var_witness2_cin = QLineEdit(self.sec_vars)
        
        # Labels follow the selected language instead of showing both at once. They
        # are kept on self so update_language() can retranslate them; anonymous
        # QLabel(...) calls in a grid cannot be reached again after construction,
        # which is why this whole section stayed bilingual whatever the setting.
        is_fr = self.lang == "fr"
        self.var_labels = {}

        def vlabel(key, fr, ar, bold=False):
            text = fr if is_fr else ar
            lb = QLabel(f"<b>{text}</b>" if bold else text, self.sec_vars)
            lb.setStyleSheet(
                "font-size:12px; font-weight:700; color:#1e3a8a; border:none;" if bold
                else "font-size:12px; color:#475569; border:none;")
            self.var_labels[key] = (lb, fr, ar, bold)
            return lb

        # Uniform control heights so the rows line up instead of stepping up and down.
        for w in (self.var_p1_name, self.var_p1_cin, self.var_p1_job, self.var_p1_addr,
                  self.var_p2_name, self.var_p2_cin, self.var_p2_job, self.var_p2_addr,
                  self.var_price_num, self.var_price_words,
                  self.var_prop_title, self.var_titre_foncier, self.var_titre_gov,
                  self.var_prop_location, self.var_prop_area,
                  self.var_witness1_name, self.var_witness1_cin,
                  self.var_witness2_name, self.var_witness2_cin):
            w.setFixedHeight(34)
        for te in (self.var_property_desc, self.var_ownership_origin):
            te.setMinimumHeight(60)
            te.setMaximumHeight(70)

        # Inputs take the space; label columns stay narrow and fixed.
        vars_grid.setColumnStretch(1, 1)
        vars_grid.setColumnStretch(3, 1)
        vars_grid.setColumnMinimumWidth(0, 130)
        vars_grid.setColumnMinimumWidth(2, 130)
        vars_grid.setVerticalSpacing(10)
        vars_grid.setHorizontalSpacing(10)

        vars_grid.addWidget(vlabel("p1", "Partie 1", "الطرف الأول", bold=True), 0, 0, 1, 4)
        vars_grid.addWidget(vlabel("p1_name", "Nom", "الاسم واللقب"), 1, 0)
        vars_grid.addWidget(self.var_p1_name, 1, 1)
        vars_grid.addWidget(vlabel("p1_cin", "CIN", "رقم بطاقة التعريف"), 1, 2)
        vars_grid.addWidget(self.var_p1_cin, 1, 3)
        vars_grid.addWidget(vlabel("p1_job", "Métier", "المهنة"), 2, 0)
        vars_grid.addWidget(self.var_p1_job, 2, 1)
        vars_grid.addWidget(vlabel("p1_addr", "Adresse", "العنوان"), 2, 2)
        vars_grid.addWidget(self.var_p1_addr, 2, 3)

        vars_grid.addWidget(vlabel("p2", "Partie 2", "الطرف الثاني", bold=True), 3, 0, 1, 4)
        vars_grid.addWidget(vlabel("p2_name", "Nom", "الاسم واللقب"), 4, 0)
        vars_grid.addWidget(self.var_p2_name, 4, 1)
        vars_grid.addWidget(vlabel("p2_cin", "CIN", "رقم بطاقة التعريف"), 4, 2)
        vars_grid.addWidget(self.var_p2_cin, 4, 3)
        vars_grid.addWidget(vlabel("p2_job", "Métier", "المهنة"), 5, 0)
        vars_grid.addWidget(self.var_p2_job, 5, 1)
        vars_grid.addWidget(vlabel("p2_addr", "Adresse", "العنوان"), 5, 2)
        vars_grid.addWidget(self.var_p2_addr, 5, 3)

        vars_grid.addWidget(vlabel("obj", "Objet du contrat", "العقار والموضوع", bold=True), 6, 0, 1, 4)
        vars_grid.addWidget(vlabel("prop_title", "Nom de l'immeuble", "اسم العقار"), 7, 0)
        vars_grid.addWidget(self.var_prop_title, 7, 1)
        vars_grid.addWidget(vlabel("titre_foncier", "N° Titre foncier", "رقم الرسم العقاري"), 7, 2)
        vars_grid.addWidget(self.var_titre_foncier, 7, 3)

        vars_grid.addWidget(vlabel("titre_gov", "Gouvernorat", "ولاية الرسم"), 8, 0)
        vars_grid.addWidget(self.var_titre_gov, 8, 1)
        vars_grid.addWidget(vlabel("prop_location", "Emplacement", "موقع العقار الكائن بـ"), 8, 2)
        vars_grid.addWidget(self.var_prop_location, 8, 3)

        vars_grid.addWidget(vlabel("prop_area", "Superficie (m²)", "المساحة (م²)"), 9, 0)
        vars_grid.addWidget(self.var_prop_area, 9, 1)

        vars_grid.addWidget(vlabel("obj_desc", "Objet et limites", "توصيف العقار والحدود"), 10, 0)
        vars_grid.addWidget(self.var_property_desc, 10, 1, 1, 3)
        vars_grid.addWidget(vlabel("obj_origin", "Origine de propriété", "أصل الملكية"), 11, 0)
        vars_grid.addWidget(self.var_ownership_origin, 11, 1, 1, 3)
        vars_grid.addWidget(vlabel("price_num", "Prix (chiffres)", "الثمن بالأرقام"), 12, 0)
        vars_grid.addWidget(self.var_price_num, 12, 1)
        vars_grid.addWidget(vlabel("price_words", "Prix (lettres)", "الثمن بالحروف"), 12, 2)
        vars_grid.addWidget(self.var_price_words, 12, 3)

        vars_grid.addWidget(vlabel("wit", "Témoins", "الشهود", bold=True), 13, 0, 1, 4)
        vars_grid.addWidget(vlabel("w1", "Témoin 1", "الشاهد الأول"), 14, 0)
        vars_grid.addWidget(self.var_witness1_name, 14, 1)
        vars_grid.addWidget(vlabel("w1_cin", "CIN témoin 1", "بطاقة الشاهد الأول"), 14, 2)
        vars_grid.addWidget(self.var_witness1_cin, 14, 3)
        vars_grid.addWidget(vlabel("w2", "Témoin 2", "الشاهد الثاني"), 15, 0)
        vars_grid.addWidget(self.var_witness2_name, 15, 1)
        vars_grid.addWidget(vlabel("w2_cin", "CIN témoin 2", "بطاقة الشاهد الثاني"), 15, 2)
        vars_grid.addWidget(self.var_witness2_cin, 15, 3)

        self.sec_vars.add_layout(vars_grid)

        self.quick_witness_btn = QPushButton(
            "Remplir les témoins" if is_fr else "تعبئة الشهود", self.sec_vars)
        self.quick_witness_btn.setProperty("class", "SecondaryButton")
        self.quick_witness_btn.clicked.connect(self.quick_fill_witnesses)
        self.sec_vars.add_widget(self.quick_witness_btn)
        
        self.refresh_vars_btn = QPushButton(("Actualiser les modifications" if self.lang == "fr" else "إعادة تحديث المحرر بالتعديلات الحالية"), self.sec_vars)
        self.refresh_vars_btn.setProperty("class", "PrimaryButton")
        self.refresh_vars_btn.clicked.connect(self.refresh_contract_preview_text)
        self.sec_vars.add_widget(self.refresh_vars_btn)
        
        left_lay.addWidget(self.sec_vars)

        # Progress bar & Actions
        self.progress_bar = QProgressBar(left_panel)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { max-height: 14px; }")
        left_lay.addWidget(self.progress_bar)

        btn_box = QHBoxLayout()
        self.generate_btn = QPushButton(("Générer le contrat officiel" if self.lang == "fr" else "توليد وصياغة العقد الرسمي النهائي"), left_panel)
        self.generate_btn.setProperty("class", "PrimaryButton")
        self.generate_btn.setMinimumHeight(45)
        self.generate_btn.clicked.connect(self.run_unified_generation)
        
        self.reset_btn = QPushButton(("Réinitialiser les documents" if self.lang == "fr" else "تصفير المستندات"), left_panel)
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

        self.copy_btn = QPushButton(("Copier le contrat" if self.lang == "fr" else "نسخ نص العقد الكامل"), right_panel)
        self.copy_btn.setProperty("class", "SecondaryButton")
        self.copy_btn.clicked.connect(self.copy_contract_text)
        right_lay.addWidget(self.copy_btn)

        # Legal Audit Controls
        self.audit_btn = QPushButton(("Vérifier le contrat et détecter les risques" if self.lang == "fr" else "فحص العقد واكتشاف الثغرات الآن"), right_panel)
        self.audit_btn.setProperty("class", "SecondaryButton")
        self.audit_btn.clicked.connect(self.run_legal_audit)
        right_lay.addWidget(self.audit_btn)

        # Audit conformité scroll area
        self.audit_scroll = QScrollArea(right_panel)
        self.audit_scroll.setWidgetResizable(True)
        self.audit_scroll.setMinimumHeight(150)
        self.audit_scroll.setStyleSheet("QScrollArea { border: 1.5px solid #cbd5e1; border-radius: 8px; background: #ffffff; }")
        
        self.audit_container = QWidget()
        self.audit_lay = QVBoxLayout(self.audit_container)
        self.audit_lay.setContentsMargins(8, 8, 8, 8)
        self.audit_lay.setSpacing(6)
        
        self.audit_status_lbl = QLabel(("Aucune vérification effectuée" if self.lang == "fr" else "لم يتم فحص العقد بعد"), self.audit_container)
        self.audit_status_lbl.setStyleSheet("color: #64748b; font-style: italic;")
        self.audit_lay.addWidget(self.audit_status_lbl)
        
        self.audit_scroll.setWidget(self.audit_container)
        right_lay.addWidget(self.audit_scroll)

        # Exports
        exports_box = QHBoxLayout()
        self.export_word_btn = QPushButton("Word (.docx)", right_panel)
        self.export_word_btn.setProperty("class", "PrimaryButton")
        self.export_word_btn.clicked.connect(self.export_word)

        self.export_pdf_btn = QPushButton("PDF (.pdf)", right_panel)
        self.export_pdf_btn.setProperty("class", "SecondaryButton")
        self.export_pdf_btn.clicked.connect(self.export_pdf)
        
        exports_box.addWidget(self.export_word_btn)
        exports_box.addWidget(self.export_pdf_btn)
        right_lay.addLayout(exports_box)

        # Multiple Archiving
        right_lay.addWidget(QLabel(("<b>Archiver le contrat dans les dossiers des clients sélectionnés :</b>" if self.lang == "fr" else "<b>حفظ وأرشفة العقد في مجلدات الحرفاء المحددين :</b>")))
        
        self.client_search_input = QLineEdit(right_panel)
        self.client_search_input.setStyleSheet("QLineEdit { padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px; }")
        self.client_search_input.textChanged.connect(self.filter_clients)
        right_lay.addWidget(self.client_search_input)

        self.client_count_lbl = QLabel("", right_panel)
        self.client_count_lbl.setWordWrap(True)
        self.client_count_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        right_lay.addWidget(self.client_count_lbl)

        self.archive_list = QListWidget(right_panel)
        self.archive_list.setMinimumHeight(120)
        self.archive_list.setStyleSheet("QListWidget { border: 1px solid #cbd5e1; border-radius: 6px; background: #ffffff; }")
        right_lay.addWidget(self.archive_list)

        self.archive_btn = QPushButton("أرشفة العقد المختار في مجلدات الحرفاء المحددين", right_panel)
        self.archive_btn.setProperty("class", "PrimaryButton")
        self.archive_btn.clicked.connect(self.archive_to_clients)
        right_lay.addWidget(self.archive_btn)

        master_scroll.setWidget(master_panel)
        self.main_layout.addWidget(master_scroll)
        
        # Initial draw
        self.rebuild_parties_ui()

    # ── IA Provider selection ──
    def filter_clients(self, text):
        """
        Searches the whole client table, not just the rows already loaded.

        Hiding rows in a list capped at 1,000 meant every client past that point was
        unreachable; the query now goes to the database so any client can be found.
        """
        q = (text or "").strip()
        if not q:
            self._populate_client_list(
                reception.get_all_clients_summary(limit=self.CLIENT_LIST_PAGE), searching=False)
            return
        self._populate_client_list(reception.search_clients_summary(q), searching=True)

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
        combo.currentIndexChanged.connect(lambda _, i=idx: on_selected(i))
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

    def on_p1_client_selected(self, idx):
        sender = self.sender()
        if isinstance(sender, QComboBox):
            self.p1_parties[idx]["client_id"] = sender.currentData()

    def on_p2_client_selected(self, idx):
        sender = self.sender()
        if isinstance(sender, QComboBox):
            self.p2_parties[idx]["client_id"] = sender.currentData()

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

        # Verify the file really is a readable image now, rather than discovering it
        # at generation time. The dialog's extension filter does not guarantee this.
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
        else:
            p_list[idx]["back_bytes"] = img_bytes
            p_list[idx]["back_lbl"] = fname
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
        """Loads the most recent clients, and says plainly how many are not shown."""
        try:
            clients = reception.get_all_clients_summary(limit=self.CLIENT_LIST_PAGE)
        except reception.DataUnavailable:
            QMessageBox.critical(
                self, "Erreur", "La liste des clients n'a pas pu être lue.")
            clients = []
        self._populate_client_list(clients, searching=False)
        self.rebuild_parties_ui()

    def _populate_client_list(self, clients, searching: bool):
        self.clients_list = []
        self.archive_list.clear()

        for c in clients:
            self.clients_list.append({
                "id": c.get("client_id"),
                "name": c.get("full_name"),
                "cin": c.get("cin_number", "—")
            })
            item = QListWidgetItem(f"{c.get('full_name')} (CIN: {c.get('cin_number', '—')})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, c.get("client_id"))
            self.archive_list.addItem(item)

        try:
            total = reception.count_clients()
        except reception.DataUnavailable:
            total = 0
        shown = len(clients)
        if searching:
            msg = f" نتائج البحث: {shown} من مجموع {total} حريف"
        elif shown < total:
            msg = (f"عرض {shown} من {total} حريف — استعمل خانة البحث للوصول إلى البقية "
                   f"(Recherchez pour atteindre les {total - shown} autres)")
        else:
            msg = f"عرض كل الحرفاء ({total})"
        if hasattr(self, "client_count_lbl"):
            self.client_count_lbl.setText(msg)
            self.client_count_lbl.setStyleSheet(
                "color: #b45309; font-size: 11px; font-weight: bold;" if shown < total
                else "color: #475569; font-size: 11px;"
            )

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
        self.refresh_contract_preview_text()

    def on_contract_type_changed(self):
        pass

    def update_ui_fields_from_state(self):
        self.var_p1_name.setText(self.contract_vars.get("party1_name", ""))
        self.var_p1_cin.setText(self.contract_vars.get("party1_cin", ""))
        self.var_p1_job.setText(self.contract_vars.get("party1_job", ""))
        self.var_p1_addr.setText(self.contract_vars.get("party1_addr", ""))
        self.var_p2_name.setText(self.contract_vars.get("party2_name", ""))
        self.var_p2_cin.setText(self.contract_vars.get("party2_cin", ""))
        self.var_p2_job.setText(self.contract_vars.get("party2_job", ""))
        self.var_p2_addr.setText(self.contract_vars.get("party2_addr", ""))
        
        self.var_property_desc.setPlainText(self.contract_vars.get("property_desc", ""))
        self.var_ownership_origin.setPlainText(self.contract_vars.get("ownership_origin", ""))
        self.var_price_num.setText(self.contract_vars.get("price_num", ""))
        self.var_price_words.setText(self.contract_vars.get("price_words", ""))
        self.var_prop_title.setText(self.contract_vars.get("property_title", ""))
        self.var_titre_foncier.setText(self.contract_vars.get("titre_foncier", ""))
        self.var_titre_gov.setText(self.contract_vars.get("titre_gov", ""))
        self.var_prop_location.setText(self.contract_vars.get("property_location", ""))
        self.var_prop_area.setText(self.contract_vars.get("property_area", ""))

    def pull_state_from_ui_fields(self):
        widget_map_text = [
            ("party1_name", self.var_p1_name),
            ("party1_cin", self.var_p1_cin),
            ("party1_job", self.var_p1_job),
            ("party1_addr", self.var_p1_addr),
            ("party2_name", self.var_p2_name),
            ("party2_cin", self.var_p2_cin),
            ("party2_job", self.var_p2_job),
            ("party2_addr", self.var_p2_addr),
            ("price_num", self.var_price_num),
            ("price_words", self.var_price_words),
            ("property_title", self.var_prop_title),
            ("titre_foncier", self.var_titre_foncier),
            ("titre_gov", self.var_titre_gov),
            ("property_location", self.var_prop_location),
            ("property_area", self.var_prop_area),
        ]
        for key, widget in widget_map_text:
            val = widget.text().strip()
            if val:
                self.contract_vars[key] = val

        for key, widget in [
            ("property_desc", self.var_property_desc),
            ("ownership_origin", self.var_ownership_origin),
        ]:
            val = widget.toPlainText().strip()
            if val:
                self.contract_vars[key] = val

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

        w1_name = self.var_witness1_name.text().strip()
        w1_data = {"name": w1_name, "cin": self.var_witness1_cin.text().strip()} if w1_name else None
        w2_name = self.var_witness2_name.text().strip()
        w2_data = {"name": w2_name, "cin": self.var_witness2_cin.text().strip()} if w2_name else None

        base_text = contract_templates.build_multi_party_contract_text(
            contract_type=self.selected_contract_type,
            party1_list=party1_list,
            party2_list=party2_list,
            procuration_text=self.procuration_input.toPlainText().strip(),
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
        self.var_witness1_name.setText("حسان بن حمودة")
        self.var_witness1_cin.setText("08123456")
        self.var_witness2_name.setText("محمد العربي الزواوي")
        self.var_witness2_cin.setText("09876543")
        self.refresh_contract_preview_text()

    def copy_contract_text(self):
        app = QApplication.instance()
        if app:
            app.clipboard().setText(self.ocr_edited_text)
            QMessageBox.information(self, "Clipboard", "تم نسخ نص العقد الكامل إلى الحافظة بنجاح!")

    # ── Audio Actions ──
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
        has_voice = bool(self.audio_bytes) or bool(self.transcription_output.toPlainText().strip())

        if not (has_p1 or has_p2 or has_voice):
            QMessageBox.warning(
                self, "Génération",
                "يرجى اختيار حريف مسجل أو إرفاق بطاقات التعريف الوطنية أو تسجيل القراءة الصوتية قبل التوليد."
            )
            return

        p1_payload = []
        for p in self.p1_parties:
            p1_payload.append({
                "client_id": p["client_id"],
                "front_bytes": p["front_bytes"],
                "back_bytes": p["back_bytes"],
                "extracted": p.get("extracted"),
                "ocr_thread": p.get("ocr_thread")
            })
            
        p2_payload = []
        for p in self.p2_parties:
            p2_payload.append({
                "client_id": p["client_id"],
                "front_bytes": p["front_bytes"],
                "back_bytes": p["back_bytes"],
                "extracted": p.get("extracted"),
                "ocr_thread": p.get("ocr_thread")
            })

        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.generate_btn.setEnabled(False)

        self.pipeline_thread = UnifiedPipelineThread(
            contract_type=self.selected_contract_type,
            p1_data=p1_payload,
            p2_data=p2_payload,
            procuration_text=self.procuration_input.toPlainText().strip(),
            audio_bytes=self.audio_bytes,
            audio_mime=self.audio_mime,
            voice_text=self.transcription_output.toPlainText(),
            api_key=self.ocr_api_key,
            provider=self.ocr_provider,
            model=self.ocr_model,
            contract_vars=self.contract_vars
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
            for k, v in ext_vars.items():
                if v:
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

        if res.get("spoken_content"):
            self.transcription_output.setPlainText(res.get("spoken_content"))
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
        self.procuration_input.clear()
        self.transcription_output.clear()
        self.audio_bytes = None
        self.audio_path_lbl.setText("لا يوجد ملف")
        self.p1_parties = [{"client_id": "", "front_bytes": None, "back_bytes": None, "front_lbl": "لا يوجد", "back_lbl": "لا يوجد"}]
        self.p2_parties = [{"client_id": "", "front_bytes": None, "back_bytes": None, "front_lbl": "لا يوجد", "back_lbl": "لا يوجد"}]

        # Clear extracted records too, so a reset cannot leak the previous act's data.
        self.p1_extracted = []
        self.p2_extracted = []
        self.extra_foussoul = []

        for i in range(self.archive_list.count()):
            self.archive_list.item(i).setCheckState(Qt.CheckState.Unchecked)
            
        self.rebuild_parties_ui()
        self.clear_layout(self.audit_lay)
        self.audit_status_lbl = QLabel(("Aucune vérification effectuée" if self.lang == "fr" else "لم يتم فحص العقد بعد"), self.audit_container)
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

    def _contract_ready_for_output(self, action_label: str) -> bool:
        """Blocks export/archiving of an empty or stub contract, which used to succeed silently."""
        text = (self.ocr_edited_text or "").strip()

        if not text:
            QMessageBox.warning(
                self, "المستند",
                f"لا يوجد نص عقد لـ{action_label}.\n"
                "يرجى توليد العقد أولاً بالضغط على «توليد وصياغة العقد الرسمي النهائي»."
            )
            return False

        if len(text) < self.MIN_CONTRACT_CHARS:
            QMessageBox.warning(
                self, "المستند",
                f"نص العقد غير مكتمل ({len(text)} حرفاً فقط) — لا يمكن {action_label}.\n"
                "يرجى إتمام صياغة العقد قبل الحفظ."
            )
            return False

        # A deed with no identified party is not a deed.
        if not (self.contract_vars.get("party1_name") or "").strip() and \
           not (self.contract_vars.get("party2_name") or "").strip():
            proceed = QMessageBox.question(
                self, "المستند",
                "لم يتم تحديد اسم أي طرف في العقد.\n\nهل تريد المتابعة رغم ذلك؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return False

        return True

    def export_word(self):
        if not self._contract_ready_for_output("التصدير بصيغة Word"):
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter en Word / حفظ بصيغة Word",
            f"{self.selected_contract_type}_{datetime.date.today()}.docx",
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

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter en PDF / حفظ بصيغة PDF",
            f"{self.selected_contract_type}_{datetime.date.today()}.pdf",
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
    def archive_to_clients(self):
        # Checked first: archiving writes into every selected client's permanent folder.
        if not self._contract_ready_for_output("الأرشفة"):
            return

        selected_client_ids = []
        selected_client_names = []

        for i in range(self.archive_list.count()):
            item = self.archive_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                cid = item.data(Qt.ItemDataRole.UserRole)
                selected_client_ids.append(cid)
                selected_client_names.append(item.text())
                
        if not selected_client_ids:
            QMessageBox.warning(self, "Archivage", "يرجى تحديد حريف واحد على الأقل من القائمة لتأمين حفظ العقد بملفهم.")
            return

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
            
            saved_count = 0
            for cid in selected_client_ids:
                fn = f"{self.selected_contract_type}_{cid}_{reception.unique_file_stamp()}.docx"
                reception.save_client_document(cid, docx_bytes, fn)
                saved_count += 1
                
            QMessageBox.information(
                self, "Archivage", 
                f" تم أرشفة وحفظ العقد بنجاح في مجلدات الحرفاء المحددين (عدد الحرفاء المربوطين: {saved_count})!"
            )
            
            for i in range(self.archive_list.count()):
                self.archive_list.item(i).setCheckState(Qt.CheckState.Unchecked)
                
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

    def open_farida_calculator(self):
        from ui.components.farida_dialog import TunisianFaridaDialog
        selected_cid = None
        if hasattr(self, "selected_p1") and self.selected_p1:
            selected_cid = self.selected_p1.get("client_id")

        dlg = TunisianFaridaDialog(self, lang=self.lang, client_id=selected_cid)
        dlg.farida_inserted.connect(self._on_farida_inserted)
        dlg.generate_partition_requested.connect(self._on_generate_partition_from_farida)
        dlg.exec()

    def _on_farida_inserted(self, farida_result: dict):
        """1-Click Direct Auto-Insert of Farida into contract editor and variables."""
        legal_text = farida_result.get("legal_notarial_text", "")
        if not legal_text:
            return

        # 1. Update contract variables state
        self.contract_vars["ownership_origin"] = legal_text
        self.contract_vars["property_desc"] = (self.contract_vars.get("property_desc", "") + f"\n{legal_text}").strip()
        if hasattr(self, "var_ownership_origin"):
            self.var_ownership_origin.setPlainText(legal_text)

        # 2. Append to procuration box if present
        if hasattr(self, "procuration_input"):
            curr_proc = self.procuration_input.toPlainText().strip()
            self.procuration_input.setText(f"{curr_proc}\n{legal_text}".strip())

        # 3. Direct insertion into the Main Contract Editor widget
        if hasattr(self, "editor") and self.editor:
            curr_editor_text = self.editor.toPlainText().strip()
            if curr_editor_text:
                self.editor.setPlainText(f"{curr_editor_text}\n\n{legal_text}")
            else:
                self.editor.setPlainText(legal_text)

        # 4. Refresh full multi-party contract preview
        try:
            self.refresh_contract_preview_text()
        except Exception:
            pass

    def _on_generate_partition_from_farida(self, farida_result: dict):
        """Auto-generates Amicable Partition Contract (عقد مقاسمة)."""
        self.select_contract_type("عقد مقاسمة")
        self._on_farida_inserted(farida_result)
