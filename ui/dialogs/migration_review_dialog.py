"""
migration_review_dialog.py — the screen where a human decides what gets imported.

This is not an optional confirmation step bolted onto an automatic import. It is
the point of the tool: the scan produces proposals, and nothing reaches the
client database until someone has looked at each one and said yes.

The layout follows what the reviewer actually has to decide:
  left   — every proposed client, ordered worst-confidence-first so the ones
           needing attention are at the top rather than buried under the easy ones
  right  — for the selected proposal: where the evidence came from, what will be
           created, which photo was chosen and why
  bottom — confirm / exclude / split / merge / correct the identity

Confidence is shown as a coloured chip AND as a word, never colour alone.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QTextEdit, QSplitter, QFrame, QProgressBar, QMessageBox,
    QLineEdit, QCheckBox, QWidget, QAbstractItemView, QInputDialog,
)

# Constants mapping for confidence style without importing legacy_migration at module scope
CONF_STYLE = {
    "HIGH":   ("#065f46", "#d1fae5", "ÉLEVÉE"),
    "MEDIUM": ("#92400e", "#fef3c7", "MOYENNE"),
    "LOW":    ("#9a3412", "#ffedd5", "FAIBLE"),
    "REVIEW": ("#991b1b", "#fee2e2", "À VÉRIFIER"),
}


class ScanThread(QThread):
    """Runs the scan off the UI thread so a 20-year archive does not freeze it."""
    tick = Signal(str, int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, root, use_ai=True, run_id=None, ai_call=None, parent=None):
        super().__init__(parent)
        self.root, self.use_ai, self.run_id, self.ai_call = root, use_ai, run_id, ai_call

    def run(self):
        try:
            import legacy_migration as lm
            plan = lm.scan_archive(
                self.root, use_ai=self.use_ai, run_id=self.run_id,
                ai_call=self.ai_call,
                progress=lambda ph, i, t, msg: self.tick.emit(ph, i, t or 0, msg),
                should_cancel=self.isInterruptionRequested)
            self.done.emit(plan)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class MigrationReviewDialog(QDialog):
    @property
    def lm(self):
        import legacy_migration
        return legacy_migration

    def __init__(self, parent=None, lang="fr"):
        super().__init__(parent)
        self.lang = lang
        self.plan = None
        self.scan_thread = None
        self.setWindowTitle("Import d'archive — révision avant écriture")
        self.setMinimumSize(1180, 780)
        self._build()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)

        head = QLabel(
            "<b>Rien n'est écrit dans la base tant que vous n'avez pas confirmé.</b><br>"
            "Chaque proposition ci-dessous vient d'une lecture automatique de "
            "l'archive. Vérifiez-la, corrigez-la si besoin, puis confirmez.", self)
        head.setWordWrap(True)
        head.setStyleSheet("background:#eff6ff; border:1px solid #bfdbfe; "
                           "border-radius:8px; padding:10px; color:#1e3a8a;")
        root.addWidget(head)

        bar = QHBoxLayout()
        self.path_input = QLineEdit(self)
        self.path_input.setPlaceholderText(r"D:\Archives_Notaire")
        self.browse_btn = QPushButton("Parcourir…", self)
        self.ai_check = QCheckBox("Lire les cartes d'identité avec l'IA (recommandé)", self)
        self.ai_check.setChecked(True)
        self.scan_btn = QPushButton("Analyser l'archive", self)
        self.scan_btn.setObjectName("PrimaryButton")
        bar.addWidget(QLabel("Dossier :", self))
        bar.addWidget(self.path_input, 4)
        bar.addWidget(self.browse_btn)
        bar.addWidget(self.ai_check)
        bar.addWidget(self.scan_btn)
        root.addLayout(bar)

        self.progress = QProgressBar(self)
        self.progress.setVisible(False)
        self.status = QLabel("", self)
        self.status.setStyleSheet("color:#475569;")
        root.addWidget(self.progress)
        root.addWidget(self.status)

        split = QSplitter(Qt.Orientation.Horizontal, self)

        left = QWidget(split)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel("", left)
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("font-size:12px; color:#334155;")
        lv.addWidget(self.summary)
        self.tree = QTreeWidget(left)
        self.tree.setHeaderLabels(["Client proposé", "CIN", "Confiance", "Fichiers", "Dossiers"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setColumnWidth(0, 300)
        self.tree.itemSelectionChanged.connect(self._on_select)
        self.tree.itemChanged.connect(self._on_item_changed)
        lv.addWidget(self.tree, 1)
        split.addWidget(left)

        right = QWidget(split)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.photo = QLabel(right)
        self.photo.setFixedHeight(150)
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setStyleSheet("border:2px dashed #cbd5e1; border-radius:8px; "
                                 "color:#64748b;")
        rv.addWidget(self.photo)
        self.detail = QTextEdit(right)
        self.detail.setReadOnly(True)
        rv.addWidget(self.detail, 1)
        split.addWidget(right)
        split.setSizes([620, 520])
        root.addWidget(split, 1)

        actions = QHBoxLayout()
        self.confirm_btn = QPushButton("Confirmer ce client", self)
        self.confirm_all_btn = QPushButton("Confirmer tous ceux sans alerte", self)
        self.exclude_btn = QPushButton("Exclure", self)
        self.split_btn = QPushButton("Séparer…", self)
        self.merge_btn = QPushButton("Fusionner la sélection", self)
        self.edit_btn = QPushButton("Corriger nom / CIN…", self)
        for b in (self.confirm_btn, self.confirm_all_btn, self.exclude_btn,
                  self.split_btn, self.merge_btn, self.edit_btn):
            actions.addWidget(b)
        root.addLayout(actions)

        foot = QHBoxLayout()
        self.commit_lbl = QLabel("", self)
        self.commit_lbl.setStyleSheet("font-weight:bold;")
        self.commit_btn = QPushButton("Importer les clients confirmés", self)
        self.commit_btn.setObjectName("PrimaryButton")
        self.close_btn = QPushButton("Fermer", self)
        foot.addWidget(self.commit_lbl, 1)
        foot.addWidget(self.commit_btn)
        foot.addWidget(self.close_btn)
        root.addLayout(foot)

        self.browse_btn.clicked.connect(self.browse)
        self.scan_btn.clicked.connect(self.start_scan)
        self.confirm_btn.clicked.connect(lambda: self.set_reviewed(True))
        self.exclude_btn.clicked.connect(self.exclude_selected)
        self.confirm_all_btn.clicked.connect(self.confirm_all_high)
        self.split_btn.clicked.connect(self.split_selected)
        self.merge_btn.clicked.connect(self.merge_selected)
        self.edit_btn.clicked.connect(self.edit_identity)
        self.commit_btn.clicked.connect(self.commit)
        self.close_btn.clicked.connect(self.reject)
        self._set_enabled(False)

    def _set_enabled(self, on: bool):
        for b in (self.confirm_btn, self.confirm_all_btn, self.exclude_btn,
                  self.split_btn, self.merge_btn, self.edit_btn, self.commit_btn):
            b.setEnabled(on)

    # ── scanning ─────────────────────────────────────────────────────────────
    def browse(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Choisir le dossier d'archive")
        if d:
            self.path_input.setText(d)

    def start_scan(self, ai_call=None):
        root = self.path_input.text().strip()
        if not root:
            QMessageBox.warning(self, "Dossier", "Indiquez le dossier de l'archive.")
            return
        self.scan_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.tree.clear()
        self.scan_thread = ScanThread(root, self.ai_check.isChecked(),
                                      ai_call=ai_call, parent=self)
        self.scan_thread.tick.connect(self._on_tick)
        self.scan_thread.done.connect(self._on_done)
        self.scan_thread.failed.connect(self._on_failed)
        self.scan_thread.start()

    def _on_tick(self, phase, i, total, msg):
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(i)
        self.status.setText(msg)

    def _on_failed(self, msg):
        self.progress.setVisible(False)
        self.scan_btn.setEnabled(True)
        QMessageBox.critical(self, "Analyse", f"L'analyse a échoué.\n\n{msg}")

    def _on_done(self, plan):
        self.plan = plan
        self.progress.setVisible(False)
        self.scan_btn.setEnabled(True)
        self._set_enabled(True)
        self.populate()

    # ── the list ─────────────────────────────────────────────────────────────
    def populate(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        if not self.plan:
            self.tree.blockSignals(False)
            return
        s = self.plan.stats
        self.summary.setText(
            f"<b>{s.get('groups', 0)}</b> client(s) proposé(s) — "
            f"<span style='color:#065f46'>{s.get('high', 0)} élevée</span>, "
            f"<span style='color:#92400e'>{s.get('medium', 0)} moyenne</span>, "
            f"<span style='color:#9a3412'>{s.get('low', 0)} faible</span>, "
            f"<span style='color:#991b1b'>{s.get('needs_review', 0)} à vérifier</span>"
            f"<br>{s.get('files_seen', 0)} fichiers lus · {s.get('ai_calls', 0)} "
            f"lectures IA · {s.get('excluded', 0)} dossiers exclus · "
            f"{s.get('unassigned', 0)} fichiers non rattachés · {s.get('seconds', 0)}s")

        for g in self.plan.groups:
            it = QTreeWidgetItem(self.tree)
            it.setData(0, Qt.ItemDataRole.UserRole, g.key)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Checked if g.reviewed
                             else Qt.CheckState.Unchecked)
            label = g.name or "(nom inconnu)"
            if g.existing_client_id:
                label += "  ↺ déjà dans la base"
            it.setText(0, label)
            it.setText(1, g.cin or "—")
            fg, bg, word = CONF_STYLE.get(getattr(g.confidence, "name", str(g.confidence)), ("#991b1b", "#fee2e2", "À VÉRIFIER"))
            it.setText(2, word)
            it.setForeground(2, Qt.GlobalColor.black)
            from PySide6.QtGui import QBrush, QColor
            it.setBackground(2, QBrush(QColor(bg)))
            it.setForeground(2, QBrush(QColor(fg)))
            it.setText(3, str(len(g.files)))
            it.setText(4, str(len(g.dossiers)))
            if g.flags:
                it.setToolTip(0, " · ".join(g.flags))
            for d in g.dossiers:
                ch = QTreeWidgetItem(it)
                ch.setText(0, f"   dossier : {d.title}")
                ch.setText(3, str(len(d.files)))
        self.tree.blockSignals(False)
        self._refresh_commit_label()

    def _selected_groups(self):
        keys = {i.data(0, Qt.ItemDataRole.UserRole)
                for i in self.tree.selectedItems()
                if i.data(0, Qt.ItemDataRole.UserRole)}
        return [g for g in (self.plan.groups if self.plan else []) if g.key in keys]

    def _on_item_changed(self, item, col):
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if not key or not self.plan:
            return
        for g in self.plan.groups:
            if g.key == key:
                g.reviewed = item.checkState(0) == Qt.CheckState.Checked
                self.lm.audit(self.plan.run_id,
                         "confirmed" if g.reviewed else "unconfirmed",
                         group_key=g.key, cin=g.cin, name=g.name,
                         confidence=g.confidence, human_edited=True)
        self._refresh_commit_label()

    def _refresh_commit_label(self):
        if not self.plan:
            return
        n = sum(1 for g in self.plan.groups if g.reviewed and g.include)
        risky = sum(1 for g in self.plan.groups
                    if g.reviewed and g.include and self.lm.is_blocked(g))
        txt = f"{n} client(s) confirmé(s) prêt(s) à importer"
        if risky:
            txt += f" — dont {risky} en confiance faible ou à vérifier"
        self.commit_lbl.setText(txt)
        self.commit_lbl.setStyleSheet(
            f"font-weight:bold; color:{'#b45309' if risky else '#065f46'};")

    # ── detail pane ──────────────────────────────────────────────────────────
    def _on_select(self):
        gs = self._selected_groups()
        if not gs:
            self.detail.clear(); self.photo.clear(); return
        fg, bg, word = CONF_STYLE.get(getattr(g.confidence, "name", str(g.confidence)), ("#991b1b", "#fee2e2", "À VÉRIFIER"))
        rows = [
            f"<h3 style='margin:0'>{g.name or '(nom inconnu)'}</h3>",
            f"<p style='margin:2px 0'><b>CIN :</b> {g.cin or '— aucun —'} &nbsp;·&nbsp; "
            f"<span style='background:{bg};color:{fg};padding:2px 8px;"
            f"border-radius:9px;font-weight:bold'>confiance {word}</span></p>",
        ]
        if g.flags:
            rows.append("<p style='color:#991b1b;margin:4px 0'><b>⚠ "
                        + " · ".join(g.flags) + "</b></p>")
        if g.existing_client_id:
            rows.append(f"<p style='color:#065f46;margin:4px 0'>Déjà dans la base : "
                        f"<code>{g.existing_client_id}</code> — {g.existing_match_reason}"
                        f"<br>Les fichiers seront ajoutés à la fiche existante.</p>")
        rows.append("<p><b>Pourquoi ce regroupement :</b></p><ul>")
        for r in g.reasons[:8]:
            rows.append(f"<li>{r}</li>")
        rows.append("</ul>")
        if len(g.name_variants) > 1:
            rows.append("<p><b>Orthographes rencontrées :</b> "
                        + ", ".join(g.name_variants) + "</p>")
        rows.append(f"<p><b>Photo choisie :</b> "
                    f"{Path(g.profile_photo).name if g.profile_photo else 'aucune'} "
                    f"— {g.photo_reason}</p>")
        if g.photo_alternatives:
            rows.append("<p style='color:#92400e'>Autres images disponibles : "
                        + ", ".join(Path(p).name for p in g.photo_alternatives[:5])
                        + "</p>")
        rows.append(f"<p><b>{len(g.dossiers)} dossier(s) à créer :</b></p><ul>")
        for d in g.dossiers:
            rows.append(f"<li>{d.title} — {len(d.files)} fichier(s) "
                        f"<i>({'; '.join(d.reasons)})</i></li>")
        rows.append("</ul>")
        rows.append(f"<p><b>{len(g.files)} fichier(s) :</b></p><ul>")
        for f in g.files[:40]:
            note = f" <span style='color:#991b1b'>[{'; '.join(f.notes)}]</span>" if f.notes else ""
            rows.append(f"<li><code>{f.rel}</code>{note}</li>")
        if len(g.files) > 40:
            rows.append(f"<li>… et {len(g.files) - 40} de plus</li>")
        rows.append("</ul>")
        rows.append("<p><b>Preuves retenues :</b></p><ul>")
        for e in g.evidence[:15]:
            rows.append(f"<li>{e.kind.upper()} <code>{e.value}</code> — {e.reason} "
                        f"<i>({e.source_path})</i></li>")
        rows.append("</ul>")
        self.detail.setHtml("".join(rows))

        if g.profile_photo and Path(g.profile_photo).exists():
            pm = QPixmap(str(g.profile_photo))
            if not pm.isNull():
                self.photo.setPixmap(pm.scaledToHeight(
                    145, Qt.TransformationMode.SmoothTransformation))
            else:
                self.photo.setText("image illisible")
        else:
            self.photo.setText("aucune photo")

    # ── reviewer actions ─────────────────────────────────────────────────────
    def set_reviewed(self, value: bool):
        for g in self._selected_groups():
            g.reviewed = value
        self.populate()

    def exclude_selected(self):
        for g in self._selected_groups():
            g.include = False
            g.reviewed = False
            self.lm.audit(self.plan.run_id, "excluded", group_key=g.key, cin=g.cin,
                     name=g.name, human_edited=True)
        self.plan.groups = [g for g in self.plan.groups if g.include]
        self.populate()

    def confirm_all_high(self):
        n = 0
        for g in self.plan.groups:
            if not self.lm.is_blocked(g):
                g.reviewed = True
                n += 1
                self.lm.audit(self.plan.run_id, "confirmed", group_key=g.key, cin=g.cin,
                         name=g.name, confidence=g.confidence, human_edited=True)
        self.populate()
        QMessageBox.information(
            self, "Confirmation",
            f"{n} client(s) en confiance élevée et sans alerte ont été confirmés.\n\n"
            f"Les autres restent à vérifier un par un.")

    def split_selected(self):
        gs = self._selected_groups()
        if len(gs) != 1:
            QMessageBox.information(self, "Séparer",
                                    "Sélectionnez un seul client à séparer.")
            return
        g = gs[0]
        names = [f.rel for f in g.files]
        pick, ok = QInputDialog.getItem(
            self, "Séparer", "Fichier à déplacer vers un nouveau client :",
            names, 0, False)
        if not ok or not pick:
            return
        new_name, ok2 = QInputDialog.getText(self, "Séparer", "Nom du nouveau client :")
        if not ok2:
            return
        self.lm.split_group(self.plan, g, [pick], new_name=new_name)
        self.populate()

    def merge_selected(self):
        gs = self._selected_groups()
        if len(gs) != 2:
            QMessageBox.information(self, "Fusionner",
                                    "Sélectionnez exactement deux clients à fusionner.")
            return
        a, b = gs
        try:
            self.lm.merge_groups(self.plan, a, b)
        except ValueError as e:
            QMessageBox.critical(self, "Fusion refusée", str(e))
            return
        self.populate()

    def edit_identity(self):
        gs = self._selected_groups()
        if len(gs) != 1:
            QMessageBox.information(self, "Corriger", "Sélectionnez un seul client.")
            return
        g = gs[0]
        name, ok = QInputDialog.getText(self, "Nom", "Nom complet :", text=g.name)
        if not ok:
            return
        cin, ok2 = QInputDialog.getText(self, "CIN", "Numéro de CIN (8 chiffres) :",
                                        text=g.cin)
        if not ok2:
            return
        if cin.strip() and not self.lm.normalise_cin(cin):
            QMessageBox.warning(self, "CIN",
                                "Un CIN tunisien comporte exactement 8 chiffres.")
            return
        self.lm.set_identity(self.plan, g, name=name.strip(), cin=cin.strip())
        self.populate()

    # ── commit ───────────────────────────────────────────────────────────────
    def commit(self):
        todo = [g for g in self.plan.groups if g.reviewed and g.include]
        if not todo:
            QMessageBox.information(
                self, "Import",
                "Aucun client n'est confirmé. Cochez ceux à importer.")
            return
        risky = [g for g in todo if self.lm.is_blocked(g)]
        msg = (f"{len(todo)} client(s) seront écrits dans la base.\n\n"
               f"Clients créés ou complétés : {len(todo)}\n"
               f"Dossiers à créer : {sum(len(g.dossiers) for g in todo)}\n"
               f"Fichiers à joindre : {sum(len(g.files) for g in todo)}")
        if risky:
            msg += (f"\n\n⚠ {len(risky)} d'entre eux sont en confiance faible ou "
                    f"marqués à vérifier :\n"
                    + "\n".join(f"  · {g.name or g.key} (CIN {g.cin or '—'})"
                                for g in risky[:8]))
        msg += "\n\nContinuer ?"
        if QMessageBox.question(self, "Confirmer l'import", msg,
                                QMessageBox.StandardButton.Yes |
                                QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != \
                QMessageBox.StandardButton.Yes:
            return
        res = self.lm.commit_plan(self.plan, [g.key for g in todo])
        QMessageBox.information(
            self, "Import terminé",
            f"Statut : {res['status']}\n"
            f"Clients créés : {res['clients_created']}\n"
            f"Fiches complétées : {res['clients_updated']}\n"
            f"Dossiers créés : {res['dossiers_created']}\n"
            f"Documents joints : {res['documents_imported']}\n"
            f"Photos : {res['photos_set']} · Empreintes : {res['faces_enrolled']}\n"
            f"Échecs : {len(res['failed'])}")
        self.accept()
