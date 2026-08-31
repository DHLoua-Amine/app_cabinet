from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QScrollArea, QMessageBox
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

# Import business logic & thread
import auth
import reception
import camera
from config import PROFILES_DIR

class FaceGridItem(QFrame):
    clicked = Signal(str) # Emits client_id on click
    dismiss_clicked = Signal(str) # Emits client_id on dismiss/delete click

    def __init__(self, face_data, lang="ar", parent=None):
        super().__init__(parent)
        self.face_data = face_data
        self.client_id = face_data.get("client_id", "")
        self.lang = lang
        self.init_ui()

    def init_ui(self):
        self.setObjectName("FaceGridItem")
        self.setProperty("class", "Card")
        
        is_known = self.face_data.get("status") == "known"
        border_color = "#10b981" if is_known else "#ef4444"
        
        self.setStyleSheet(f"""
            QFrame#FaceGridItem {{
                background-color: #ffffff;
                border: 2px solid {border_color};
                border-radius: 8px;
            }}
            QFrame#FaceGridItem:hover {{
                background-color: #f8fafc;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if not is_known:
            self.setFixedSize(115, 145)
        else:
            self.setFixedSize(115, 120)

        # Top Header for Unknown Item (Delete Button)
        if not is_known:
            top_bar = QHBoxLayout()
            top_bar.setContentsMargins(0, 0, 0, 0)
            top_bar.addStretch()
            
            self.del_btn = QPushButton("✕", self)
            self.del_btn.setFixedSize(20, 20)
            self.del_btn.setToolTip("إلغاء / حذف هذا الزائر" if self.lang == "ar" else "Ignorer / Supprimer")
            self.del_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ef4444;
                    color: #ffffff;
                    border: none;
                    border-radius: 10px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #dc2626;
                }
            """)
            self.del_btn.clicked.connect(self._on_del_clicked)
            top_bar.addWidget(self.del_btn)
            layout.addLayout(top_bar)

        # Image Label
        self.img_lbl = QLabel(self)
        self.img_lbl.setFixedSize(80, 80)
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        qimg = self.face_data.get("crop_qimg")
        if qimg and not qimg.isNull():
            self.img_lbl.setPixmap(QPixmap.fromImage(qimg).scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            self.img_lbl.setText("")
            self.img_lbl.setStyleSheet("font-size: 32px; color: #64748b; background-color: #e2e8f0; border-radius: 40px;")
            
        layout.addWidget(self.img_lbl)

        # Label Name
        name = self.face_data.get("name", "")
        self.name_lbl = QLabel(name, self)
        self.name_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #0f172a;")
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name_lbl)

    def _on_del_clicked(self):
        self.dismiss_clicked.emit(self.client_id)

    def mousePressEvent(self, event):
        self.clicked.emit(self.client_id)
        super().mousePressEvent(event)


class HomePage(QWidget):
    # Emitted when we open the client file
    client_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang = auth.session_state.lang
        self.session_faces = {}  # Persistent session accumulation across all frames
        self.dismissed_unknown_ids = set()
        self.camera_service = None
        self.selected_face_id = None
        
        self.init_ui()
        self.init_camera_config()

    def init_ui(self):
        # Master Outer Vertical Layout
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ── MASTER VERTICAL SCROLL AREA (Allows full page vertical sweep/scroll) ──
        self.main_scroll = QScrollArea(self)
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        content_widget = QWidget()
        content_widget.setObjectName("HomePageContent")
        content_widget.setStyleSheet("QWidget#HomePageContent { background-color: transparent; }")
        
        self.main_layout = QVBoxLayout(content_widget)
        self.main_layout.setContentsMargins(30, 20, 30, 20)
        self.main_layout.setSpacing(16)

        # ── 1. Two Columns Layout (Camera Stream / Quick Fiche) ──────────────
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(20)

        # A. Left Column: Camera Viewport
        camera_col = QVBoxLayout()
        camera_col.setSpacing(10)

        # Viewport Label
        self.video_viewport = QLabel(self)
        self.video_viewport.setFixedSize(640, 420)
        self.video_viewport.setStyleSheet("""
            QLabel {
                background-color: #e2e8f0;
                border: 2px dashed #cbd5e1;
                border-radius: 12px;
                color: #475569;
                font-size: 15px;
                font-weight: bold;
            }
        """)
        self.video_viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.show_camera_disconnected_message()
        camera_col.addWidget(self.video_viewport)

        # Control Panel Box
        cam_panel = QFrame(self)
        cam_panel.setProperty("class", "Card")
        cam_panel_layout = QHBoxLayout(cam_panel)
        cam_panel_layout.setContentsMargins(12, 8, 12, 8)
        cam_panel_layout.setSpacing(15)

        self.cam_hint_lbl = QLabel("", cam_panel)
        self.cam_hint_lbl.setStyleSheet("color:#64748b; font-size:11px; border:none;")

        self.connect_btn = QPushButton("Connecter la Caméra", cam_panel)
        self.connect_btn.setProperty("class", "PrimaryButton")
        self.connect_btn.clicked.connect(self.toggle_camera)

        cam_panel_layout.addWidget(self.cam_hint_lbl)
        cam_panel_layout.addStretch()
        cam_panel_layout.addWidget(self.connect_btn)
        self.refresh_camera_hint()

        camera_col.addWidget(cam_panel)
        columns_layout.addLayout(camera_col, stretch=2)

        # B. Right Column: Quick Fiche Sidebar
        self.fiche_panel = QFrame(self)
        self.fiche_panel.setProperty("class", "Card")
        self.fiche_panel.setFixedWidth(380)
        self.fiche_panel_layout = QVBoxLayout(self.fiche_panel)
        self.fiche_panel_layout.setContentsMargins(16, 16, 16, 16)
        self.fiche_panel_layout.setSpacing(10)

        self.fiche_header = QLabel("بطاقة سريعة بالاستقبال / Fiche Rapide", self.fiche_panel)
        self.fiche_header.setStyleSheet("font-weight: 800; font-size: 14px; color: #1e3a8a;")
        self.fiche_panel_layout.addWidget(self.fiche_header)
        
        self.fiche_content = QWidget(self.fiche_panel)
        self.fiche_content_layout = QVBoxLayout(self.fiche_content)
        self.fiche_content_layout.setContentsMargins(0, 0, 0, 0)
        self.fiche_content_layout.setSpacing(8)
        
        self.quick_avatar = QLabel(self.fiche_content)
        self.quick_avatar.setFixedSize(90, 90)
        self.quick_avatar.setStyleSheet("border-radius: 45px; background-color: #e2e8f0;")
        self.quick_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.quick_status = QLabel(self.fiche_content)
        self.quick_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.quick_name = QLabel(self.fiche_content)
        self.quick_name.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a;")
        self.quick_name.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.quick_details = QLabel(self.fiche_content)
        self.quick_details.setStyleSheet("font-size: 12px; color: #475569;")
        self.quick_details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.quick_action_btn = QPushButton(self.fiche_content)
        self.quick_action_btn.setProperty("class", "PrimaryButton")
        self.quick_action_btn.clicked.connect(self.on_quick_action_clicked)

        self.quick_delete_btn = QPushButton("حذف الزائر من القائمة", self.fiche_content)
        self.quick_delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #fef2f2;
                color: #dc2626;
                border: 1px solid #fca5a5;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #fee2e2;
            }
        """)
        self.quick_delete_btn.clicked.connect(self.on_sidebar_delete_clicked)
        self.quick_delete_btn.setVisible(False)

        self.fiche_content_layout.addWidget(self.quick_avatar, alignment=Qt.AlignmentFlag.AlignCenter)
        self.fiche_content_layout.addWidget(self.quick_status, alignment=Qt.AlignmentFlag.AlignCenter)
        self.fiche_content_layout.addWidget(self.quick_name, alignment=Qt.AlignmentFlag.AlignCenter)
        self.fiche_content_layout.addWidget(self.quick_details, alignment=Qt.AlignmentFlag.AlignCenter)
        self.fiche_content_layout.addWidget(self.quick_action_btn)
        self.fiche_content_layout.addWidget(self.quick_delete_btn)
        
        self.fiche_panel_layout.addWidget(self.fiche_content)
        self.fiche_content.setVisible(False)

        # Instructions Label if empty
        self.inst_lbl = QLabel("Sélectionnez un visage dans la grille ci-dessous pour afficher son profil.", self.fiche_panel)
        self.inst_lbl.setStyleSheet("color: #64748b; font-style: italic;")
        self.inst_lbl.setWordWrap(True)
        self.inst_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fiche_panel_layout.addWidget(self.inst_lbl)

        columns_layout.addWidget(self.fiche_panel, stretch=1)
        self.main_layout.addLayout(columns_layout)

        # ── 2. SEPARATE SECTION 1: 🟢 الحرفاء المسجلون المعرفون (Known Clients) ──
        known_bar = QHBoxLayout()
        self.known_header = QLabel("🟢 الحرفاء المسجلون المعرفون", self)
        self.known_header.setStyleSheet("font-weight: bold; font-size: 13px; color: #047857;")
        known_bar.addWidget(self.known_header)
        known_bar.addStretch()

        self.clear_known_btn = QPushButton("مسح القائمة / Effacer", self)
        self.clear_known_btn.setStyleSheet("font-size: 10px; color: #64748b; background: transparent; border: none;")
        self.clear_known_btn.clicked.connect(self.clear_known_history)
        known_bar.addWidget(self.clear_known_btn)
        self.main_layout.addLayout(known_bar)

        self.known_scroll = QScrollArea(self)
        self.known_scroll.setWidgetResizable(True)
        self.known_scroll.setStyleSheet("QScrollArea { border: 1px solid #e2e8f0; border-radius: 8px; background-color: #f8fafc; }")
        self.known_scroll.setFixedHeight(145)
        
        self.known_container = QWidget()
        self.known_container.setObjectName("KnownContainer")
        self.known_container.setStyleSheet("QWidget#KnownContainer { background-color: transparent; }")
        self.known_grid_layout = QHBoxLayout(self.known_container)
        self.known_grid_layout.setSpacing(12)
        self.known_grid_layout.setContentsMargins(8, 8, 8, 8)
        self.known_grid_layout.addStretch()
        
        self.known_scroll.setWidget(self.known_container)
        self.main_layout.addWidget(self.known_scroll)

        # ── 3. SEPARATE SECTION 2: 🔴 الزوار الجدد غير المسجلين (Unknown Visitors) ──
        unknown_bar = QHBoxLayout()
        self.unknown_header = QLabel("🔴 الزوار الجدد غير المسجلين (يمكنك حذف الزائر إذا أخطأت الكاميرا)", self)
        self.unknown_header.setStyleSheet("font-weight: bold; font-size: 13px; color: #b91c1c;")
        unknown_bar.addWidget(self.unknown_header)
        unknown_bar.addStretch()

        self.clear_unknown_btn = QPushButton("مسح الكل / Tout effacer", self)
        self.clear_unknown_btn.setStyleSheet("font-size: 10px; color: #64748b; background: transparent; border: none;")
        self.clear_unknown_btn.clicked.connect(self.clear_unknown_history)
        unknown_bar.addWidget(self.clear_unknown_btn)
        self.main_layout.addLayout(unknown_bar)

        self.unknown_scroll = QScrollArea(self)
        self.unknown_scroll.setWidgetResizable(True)
        self.unknown_scroll.setStyleSheet("QScrollArea { border: 1px solid #fee2e2; border-radius: 8px; background-color: #fff5f5; }")
        self.unknown_scroll.setFixedHeight(175)
        
        self.unknown_container = QWidget()
        self.unknown_container.setObjectName("UnknownContainer")
        self.unknown_container.setStyleSheet("QWidget#UnknownContainer { background-color: transparent; }")
        self.unknown_grid_layout = QHBoxLayout(self.unknown_container)
        self.unknown_grid_layout.setSpacing(12)
        self.unknown_grid_layout.setContentsMargins(8, 8, 8, 8)
        self.unknown_grid_layout.addStretch()
        
        self.unknown_scroll.setWidget(self.unknown_container)
        self.main_layout.addWidget(self.unknown_scroll)

        self.main_scroll.setWidget(content_widget)
        outer_layout.addWidget(self.main_scroll)

        self.update_translations()

    def update_translations(self):
        is_fr = self.lang == "fr"
        self.refresh_camera_hint()
        self.fiche_header.setText("Fiche Rapide Guichet" if is_fr else "بطاقة سريعة بالاستقبال")
        self.inst_lbl.setText("Cliquez sur un visage capturé en bas pour afficher son profil." if is_fr else "انقر على وجه تم التقاطه بالأسفل لعرض ملفه بالكامل.")
        self.known_header.setText("🟢 Clients Enregistrés" if is_fr
                                  else "🟢 الحرفاء المسجلون المعرفون")
        self.unknown_header.setText("🔴 Visiteurs Inconnus (Ignorer/Supprimer)" if is_fr else "🔴 الزوار الجدد غير المسجلين (يمكنك حذف الزائر إذا أخطأت الكاميرا)")
        self.clear_known_btn.setText("Effacer" if is_fr else "مسح القائمة")
        self.clear_unknown_btn.setText("Tout effacer" if is_fr else "مسح الكل")

        svc = self.camera_service
        if svc is not None and svc.is_running():
            self.connect_btn.setText("Déconnecter" if is_fr else "قطع الاتصال")
        else:
            self.connect_btn.setText("Connecter la Caméra" if is_fr else "ربط الكاميرا")

        if is_fr:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    # ── Shared camera service ────────────────────────────────────────────────
    def attach_camera_service(self, service):
        """Called once by MainWindow. This page renders the feed; it does not own it."""
        self.camera_service = service
        service.frame_ready.connect(self.on_frame_received)
        service.status_changed.connect(self.on_service_status)
        self.on_service_status(service.state, service.detail)

    def on_service_status(self, state, detail=""):
        """Reflects the service's state in this page's own controls."""
        is_fr = self.lang == "fr"
        connected = state == "connected"
        if hasattr(self, "connect_btn"):
            self.connect_btn.setText(
                ("Déconnecter" if is_fr else "قطع الاتصال") if connected
                else ("Connecter la Caméra" if is_fr else "ربط الكاميرا"))
        if not connected and hasattr(self, "video_viewport"):
            self.show_camera_disconnected_message()

    def init_camera_config(self):
        self.refresh_camera_hint()

    def refresh_camera_hint(self):
        is_fr = self.lang == "fr"
        if not camera.has_saved_camera_source():
            self.cam_hint_lbl.setText(
                "Aucune caméra configurée — voir Paramètres" if is_fr
                else "لم يتم إعداد كاميرا — انظر الإعدادات")
            return
        src = camera.get_saved_camera_source()
        if isinstance(src, str) and src:
            self.cam_hint_lbl.setText(
                f"Caméra IP : {src}" if is_fr else f"كاميرا الشبكة : {src}")
        else:
            self.cam_hint_lbl.setText(
                f"Caméra USB {src} (modifiable dans Paramètres)" if is_fr
                else f"كاميرا USB رقم {src} (تُغيَّر من الإعدادات)")

    def show_camera_disconnected_message(self):
        self.video_viewport.clear()
        self.video_viewport.setText(("\nCaméra désactivée" if self.lang == "fr" else "\nالكاميرا غير متصلة"))

    def toggle_camera(self):
        svc = self.camera_service
        if svc is not None and svc.is_running():
            self.stop_camera()
        else:
            self.start_camera()

    def start_camera(self):
        is_fr = self.lang == "fr"
        if not camera.has_saved_camera_source():
            QMessageBox.warning(
                self, "Caméra" if is_fr else "الكاميرا",
                "Aucune caméra n'est configurée. Ouvrez Paramètres pour en choisir une."
                if is_fr else
                "لم يتم إعداد أي كاميرا. افتح صفحة الإعدادات لاختيار الكاميرا.")
            return
        if self.camera_service is None:
            return
        self.camera_service.set_preview_enabled(True)
        self.camera_service.restart(camera.get_saved_camera_source())

    def stop_camera(self):
        if self.camera_service is not None:
            self.camera_service.stop()
        self.show_camera_disconnected_message()
        self.connect_btn.setText("Connecter la Caméra" if self.lang == "fr" else "ربط الكاميرا")

    def dismiss_unknown_visitor(self, client_id: str):
        """Dismisses an unknown visitor manually so they disappear from the screen."""
        self.dismissed_unknown_ids.add(client_id)
        if client_id in self.session_faces:
            del self.session_faces[client_id]
        if self.selected_face_id == client_id:
            self.selected_face_id = None
            self.fiche_content.setVisible(False)
            self.inst_lbl.setVisible(True)
        self._rebuild_grids()

    def clear_known_history(self):
        to_del = [cid for cid, f in self.session_faces.items() if f.get("status") == "known"]
        for cid in to_del:
            del self.session_faces[cid]
        if self.selected_face_id in to_del:
            self.selected_face_id = None
            self.fiche_content.setVisible(False)
            self.inst_lbl.setVisible(True)
        self._rebuild_grids()

    def clear_unknown_history(self):
        to_del = [cid for cid, f in self.session_faces.items() if f.get("status") != "known"]
        for cid in to_del:
            self.dismissed_unknown_ids.add(cid)
            del self.session_faces[cid]
        if self.selected_face_id in to_del:
            self.selected_face_id = None
            self.fiche_content.setVisible(False)
            self.inst_lbl.setVisible(True)
        self._rebuild_grids()

    def on_sidebar_delete_clicked(self):
        if self.selected_face_id and self.selected_face_id in self.session_faces:
            self.dismiss_unknown_visitor(self.selected_face_id)

    @Slot(QImage, list)
    def on_frame_received(self, qimg, detected_list):
        # 1. Update Viewport image
        self.video_viewport.setPixmap(QPixmap.fromImage(qimg).scaled(640, 420, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        # 2. Accumulate all detected faces into persistent session storage
        changed = False
        for face in detected_list:
            cid = face.get("client_id")
            if not cid or cid in self.dismissed_unknown_ids:
                continue

            # If an unknown face gets recognized as known on subsequent frames, update its status!
            if cid not in self.session_faces:
                self.session_faces[cid] = face
                changed = True
            else:
                # Update crop or status if it improved from unknown to known
                existing = self.session_faces[cid]
                if face.get("status") == "known" and existing.get("status") != "known":
                    self.session_faces[cid] = face
                    changed = True
                elif face.get("crop_qimg") and not face["crop_qimg"].isNull():
                    self.session_faces[cid]["crop_qimg"] = face["crop_qimg"]

        if changed:
            self._rebuild_grids()
            if self.session_faces and not self.selected_face_id:
                first_id = list(self.session_faces.keys())[0]
                self.on_face_selected(first_id)

    def _rebuild_grids(self):
        # Clear known layout
        for i in reversed(range(self.known_grid_layout.count())):
            item = self.known_grid_layout.takeAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        # Clear unknown layout
        for i in reversed(range(self.unknown_grid_layout.count())):
            item = self.unknown_grid_layout.takeAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        active_faces = list(self.session_faces.values())
        known_faces = [f for f in active_faces if f.get("status") == "known"]
        unknown_faces = [f for f in active_faces if f.get("status") != "known" and f.get("client_id") not in self.dismissed_unknown_ids]

        # Populate Known Grid
        for face in known_faces:
            item_widget = FaceGridItem(face, lang=self.lang, parent=self.known_container)
            item_widget.clicked.connect(self.on_face_selected)
            self.known_grid_layout.insertWidget(0, item_widget)

        # Populate Unknown Grid
        for face in unknown_faces:
            item_widget = FaceGridItem(face, lang=self.lang, parent=self.unknown_container)
            item_widget.clicked.connect(self.on_face_selected)
            item_widget.dismiss_clicked.connect(self.dismiss_unknown_visitor)
            self.unknown_grid_layout.insertWidget(0, item_widget)

    def on_face_selected(self, client_id):
        self.selected_face_id = client_id
        if client_id not in self.session_faces:
            return

        face = self.session_faces[client_id]
        is_known = face.get("status") == "known"
        is_fr = self.lang == "fr"

        self.inst_lbl.setVisible(False)
        self.fiche_content.setVisible(True)

        # Avatar
        qimg = face.get("crop_qimg")
        if qimg and not qimg.isNull():
            self.quick_avatar.setPixmap(QPixmap.fromImage(qimg).scaled(90, 90, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))

        # Status & Details
        if is_known:
            self.quick_status.setText("Client Enregistré" if is_fr else "حريف مسجل معروف")
            self.quick_status.setStyleSheet("color: #10b981; font-weight: bold; font-size: 12px;")
            self.quick_name.setText(face.get("name", ""))
            
            c_info = reception.get_client_by_id(client_id)
            phone = c_info.get("phone", "—") if c_info else "—"
            cin = c_info.get("cin_number", "—") if c_info else "—"
            self.quick_details.setText(f" Tél: {phone}\n CIN: {cin}")
            
            self.quick_action_btn.setText("Fiche Client / فتح الملف" if is_fr else "فتح بطاقة الحريف")
            self.quick_delete_btn.setVisible(False)
        else:
            self.quick_status.setText("Visiteur Nouveau" if is_fr else "زائر جديد بالاستقبال")
            self.quick_status.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 12px;")
            self.quick_name.setText("Nouveau Client" if is_fr else "زائر جديد")
            self.quick_details.setText("Aucune donnée disponible" if is_fr else "لا توجد معطيات بالملف")
            
            self.quick_action_btn.setText("Créer une fiche / تسجيل" if is_fr else "إنشاء بطاقة حريف")
            self.quick_delete_btn.setText("Supprimer de la liste" if is_fr
                                          else "حذف الزائر من القائمة")
            self.quick_delete_btn.setVisible(True)

    def on_quick_action_clicked(self):
        if not self.selected_face_id:
            return
            
        face = self.session_faces.get(self.selected_face_id)
        if not face:
            return

        is_known = face.get("status") == "known"

        if is_known:
            self.client_selected.emit(self.selected_face_id)
        else:
            qimg = face.get("crop_qimg")
            if qimg and not qimg.isNull():
                temp_id = reception.generate_client_id()
                PROFILES_DIR.mkdir(parents=True, exist_ok=True)
                target_path = PROFILES_DIR / f"{temp_id}.jpg"
                
                try:
                    qimg.save(str(target_path), "JPG")
                    created = reception.update_client_civil_status(
                        client_id=temp_id, nom="", prenom="", phone="", maiden_name="",
                        birth_date="01/01/1990", birth_place="", cin_number="", cin_date_place="",
                        marital_status="أعزب", matrimonial_regime="", profession="", address="",
                        legal_role="مشتري", company_name="", company_rc=""
                    )
                    if not created:
                        QMessageBox.critical(self, "خطأ", "تعذّر إنشاء بطاقة الحريف الجديدة!")
                        return

                    reception.update_client_profile_pic(temp_id, str(target_path))
                    
                    emb = face.get("embedding")
                    if emb is not None:
                        from reception import serialize_embedding
                        try:
                            blob = serialize_embedding(emb)
                            conn = reception.get_connection()
                            cursor = conn.cursor()
                            cursor.execute("UPDATE clients SET face_embedding=? WHERE client_id=?", (blob, temp_id))
                            conn.commit()
                            conn.close()
                        except Exception as emb_err:
                            reception.log_system_error("quick registration embedding error", emb_err)
                    
                    self.client_selected.emit(temp_id)
                except Exception as e:
                    QMessageBox.warning(self, "Erreur", f"Erreur de création: {e}")
            else:
                self.client_selected.emit("NEW")

    # Parent notification triggers
    def showEvent(self, event):
        if self.camera_service is not None:
            self.camera_service.set_preview_enabled(True)
        super().showEvent(event)

    def hideEvent(self, event):
        if self.camera_service is not None:
            self.camera_service.set_preview_enabled(False)
        super().hideEvent(event)

    def update_language(self, lang_code):
        self.lang = lang_code
        self.update_translations()
