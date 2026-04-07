from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .graphics_items import EdgeItem, NodeItem
from .templates import NODE_TEMPLATES


class FlowGraphicsView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, editor) -> None:
        super().__init__(scene)
        self.editor = editor
        self.setMouseTracking(True)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self.editor.handle_port_click(scene_pos):
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        self.editor.handle_port_hover(scene_pos)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.editor.handle_port_hover(None)
        super().leaveEvent(event)

    def drawForeground(self, painter: QPainter, rect) -> None:
        super().drawForeground(painter, rect)
        self.editor.draw_port_preview(painter)


class MermaidFlowEditor(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Flow Rebuild - Mermaid Editor")
        self.resize(1400, 900)

        self.node_counter = 1
        self.nodes: Dict[str, NodeItem] = {}
        self.edges: List[EdgeItem] = []

        self.port_connect_mode = False
        self.pending_source_port: Optional[Tuple[NodeItem, str]] = None
        self.hovered_input_port: Optional[Tuple[NodeItem, str]] = None
        self.hovered_output_port: Optional[Tuple[NodeItem, str]] = None
        self.preview_scene_pos: Optional[QPointF] = None

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-2600, -2600, 5200, 5200)
        self.scene.selectionChanged.connect(self.on_selection_changed)

        self.view = FlowGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.Antialiasing, True)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)

        self.template_list = QListWidget()
        self.template_list.setMinimumWidth(190)
        for key, data in NODE_TEMPLATES.items():
            item = QListWidgetItem(f"{data['label']} ({key})")
            item.setData(Qt.UserRole, key)
            self.template_list.addItem(item)
        self.template_list.itemDoubleClicked.connect(self.add_node_from_template)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Templates (double-click to add)"))
        left_layout.addWidget(QLabel("Resize from corner; drag into another node to nest"))
        left_layout.addWidget(self.template_list)
        self.btn_add = QPushButton("Add Selected Template")
        self.btn_add.clicked.connect(self.add_selected_template)
        left_layout.addWidget(self.btn_add)

        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.addWidget(self.view)

        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(center_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._build_property_dock()
        self._build_toolbar()

        self.mermaid_preview = QTextEdit()
        self.mermaid_preview.setReadOnly(True)
        preview_dock = QDockWidget("Mermaid Preview", self)
        preview_dock.setWidget(self.mermaid_preview)
        self.addDockWidget(Qt.BottomDockWidgetArea, preview_dock)

        self._seed_program_flow_example()
        self.refresh_mermaid_preview()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        self.addToolBar(toolbar)

        self.act_port_mode = QAction("Port Connect Mode", self)
        self.act_port_mode.setCheckable(True)
        self.act_port_mode.toggled.connect(self.toggle_port_connect_mode)
        toolbar.addAction(self.act_port_mode)

        act_connect = QAction("Connect Selected Nodes", self)
        act_connect.triggered.connect(self.connect_selected_nodes)
        toolbar.addAction(act_connect)

        act_nest = QAction("Nest (child -> parent)", self)
        act_nest.triggered.connect(self.nest_selected_nodes)
        toolbar.addAction(act_nest)

        act_unnest = QAction("Unnest", self)
        act_unnest.triggered.connect(self.unnest_selected_nodes)
        toolbar.addAction(act_unnest)

        act_delete = QAction("Delete Selected", self)
        act_delete.triggered.connect(self.delete_selected)
        toolbar.addAction(act_delete)

        act_export = QAction("Export .mmd", self)
        act_export.triggered.connect(self.export_mermaid_file)
        toolbar.addAction(act_export)

        act_import = QAction("Import .mmd", self)
        act_import.triggered.connect(self.import_mermaid_file)
        toolbar.addAction(act_import)

    def _build_property_dock(self) -> None:
        self.title_input = QLineEdit()
        self.type_input = QComboBox()
        self.type_input.addItems(NODE_TEMPLATES.keys())

        self.width_input = QSpinBox()
        self.width_input.setRange(140, 3000)
        self.width_input.setValue(230)

        self.height_input = QSpinBox()
        self.height_input.setRange(90, 3000)
        self.height_input.setValue(130)

        self.inputs_input = QTextEdit()
        self.outputs_input = QTextEdit()
        self.members_input = QTextEdit()
        self.description_input = QTextEdit()

        self.inputs_input.setPlaceholderText("One input per line")
        self.outputs_input.setPlaceholderText("One output per line")
        self.members_input.setPlaceholderText("One member per line")
        self.description_input.setPlaceholderText("Describe behavior, boundaries, constraints...")

        self.btn_apply = QPushButton("Apply to Selected Node(s)")
        self.btn_apply.clicked.connect(self.apply_properties_to_selected)

        panel = QWidget()
        layout = QFormLayout(panel)
        layout.addRow("Title", self.title_input)
        layout.addRow("Type", self.type_input)
        layout.addRow("Width", self.width_input)
        layout.addRow("Height", self.height_input)
        layout.addRow("Inputs", self.inputs_input)
        layout.addRow("Outputs", self.outputs_input)
        layout.addRow("Members", self.members_input)
        layout.addRow("Description", self.description_input)
        layout.addRow(self.btn_apply)

        dock = QDockWidget("Node Properties", self)
        dock.setWidget(panel)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _seed_program_flow_example(self) -> None:
        n1 = self.create_node("interface", "main.py", "Application entry point", outputs=["run()"])
        n1.setPos(-430, -100)

        n2 = self.create_node(
            "function",
            "run()",
            "Create QApplication, build editor, start event loop",
            inputs=["main.py"],
            outputs=["Qt event loop"],
        )
        n2.setPos(-120, -100)

        n3 = self.create_node(
            "class",
            "MermaidFlowEditor.__init__()",
            "Initialize scene, view, docks, toolbar, and initial graph",
            outputs=["ready editor"],
        )
        n3.setPos(220, -150)

        n4 = self.create_node(
            "process",
            "Port Connect Mode",
            "Output port to input port connection with hover highlight and preview curve",
            inputs=["mouse events"],
            outputs=["EdgeItem"],
        )
        n4.setPos(610, -150)

        self.add_edge(n1, n2, "main.py -> run()", "run()", "main.py")
        self.add_edge(n2, n3, "instantiate editor", "Qt event loop", "ready editor")
        self.add_edge(n3, n4, "create interaction flow", "ready editor", "mouse events")

    def toggle_port_connect_mode(self, enabled: bool) -> None:
        self.port_connect_mode = enabled
        self.pending_source_port = None
        self.hovered_input_port = None
        self.hovered_output_port = None
        self.preview_scene_pos = None
        self._update_port_highlights()
        self.view.viewport().update()
        message = "Port connect mode ON" if enabled else "Port connect mode OFF"
        self.statusBar().showMessage(message, 2500)

    def _node_at_scene_pos(self, scene_pos: QPointF) -> Optional[NodeItem]:
        for item in self.scene.items(scene_pos):
            if isinstance(item, NodeItem):
                return item
        return None

    def _update_port_highlights(self) -> None:
        selected_source = self.pending_source_port
        for node in self.nodes.values():
            hover_input = None
            hover_output = None
            selected_output = None

            if self.hovered_input_port and self.hovered_input_port[0] is node:
                hover_input = self.hovered_input_port[1]
            if self.hovered_output_port and self.hovered_output_port[0] is node:
                hover_output = self.hovered_output_port[1]
            if selected_source and selected_source[0] is node:
                selected_output = selected_source[1]

            node.set_port_highlight(hover_input, hover_output, selected_output)

    def handle_port_hover(self, scene_pos: Optional[QPointF]) -> None:
        if not self.port_connect_mode:
            return

        self.preview_scene_pos = scene_pos
        self.hovered_input_port = None
        self.hovered_output_port = None

        if scene_pos is not None:
            node = self._node_at_scene_pos(scene_pos)
            if node is not None:
                out_name = node.output_port_hit_test(scene_pos)
                in_name = node.input_port_hit_test(scene_pos)
                if out_name:
                    self.hovered_output_port = (node, out_name)
                if in_name:
                    self.hovered_input_port = (node, in_name)

        self._update_port_highlights()
        self.view.viewport().update()

    def draw_port_preview(self, painter: QPainter) -> None:
        if not self.port_connect_mode or self.pending_source_port is None:
            return

        source_node, source_port = self.pending_source_port
        start = source_node.output_port_scene_pos(source_port)
        end = self.preview_scene_pos or start

        if self.hovered_input_port is not None:
            hover_node, hover_input = self.hovered_input_port
            end = hover_node.input_port_scene_pos(hover_input)

        path = QPainterPath(start)
        dx = (end.x() - start.x()) * 0.5
        c1 = QPointF(start.x() + dx, start.y())
        c2 = QPointF(end.x() - dx, end.y())
        path.cubicTo(c1, c2, end)

        painter.save()
        painter.setPen(QPen(QColor("#ff8a3d"), 2, Qt.DashLine))
        painter.drawPath(path)
        painter.restore()

    def handle_port_click(self, scene_pos: QPointF) -> bool:
        if not self.port_connect_mode:
            return False

        self.preview_scene_pos = scene_pos
        node = self._node_at_scene_pos(scene_pos)
        if node is None:
            return False

        output_name = node.output_port_hit_test(scene_pos)
        input_name = node.input_port_hit_test(scene_pos)

        if self.pending_source_port is None:
            if output_name:
                self.pending_source_port = (node, output_name)
                self._update_port_highlights()
                self.view.viewport().update()
                self.statusBar().showMessage(f"Source selected: {node.node_id}.{output_name}", 2000)
                return True
            self.statusBar().showMessage("Click an output port first", 2000)
            return True

        source_node, source_port = self.pending_source_port

        if output_name:
            self.pending_source_port = (node, output_name)
            self._update_port_highlights()
            self.view.viewport().update()
            self.statusBar().showMessage(f"Source switched: {node.node_id}.{output_name}", 2000)
            return True

        if not input_name:
            self.statusBar().showMessage("Click a target input port", 2000)
            return True

        if source_node is node:
            self.statusBar().showMessage("Self-link inside the same node is not allowed", 2000)
            return True

        label = f"{source_port} -> {input_name}"
        self.add_edge(source_node, node, label, source_port, input_name)
        self.pending_source_port = None
        self._update_port_highlights()
        self.view.viewport().update()
        self.statusBar().showMessage("Edge created", 2000)
        return True

    def add_selected_template(self) -> None:
        current = self.template_list.currentItem()
        if current is None:
            QMessageBox.information(self, "Hint", "Select a template from the list first.")
            return
        self.add_node_from_template(current)

    def add_node_from_template(self, item: QListWidgetItem) -> None:
        node_type = item.data(Qt.UserRole)
        title, ok = QInputDialog.getText(self, "New Node", "Node title:", text=f"New {node_type}")
        if not ok:
            return

        description, ok = QInputDialog.getMultiLineText(
            self,
            "New Node",
            "Node description:",
            "Describe behavior and boundaries...",
        )
        if not ok:
            return

        node = self.create_node(node_type, title.strip() or f"New {node_type}", description.strip())
        center = self.view.mapToScene(self.view.viewport().rect().center())
        node.setPos(center)
        self.refresh_mermaid_preview()

    def create_node(
        self,
        node_type: str,
        title: str,
        description: str,
        inputs: Optional[List[str]] = None,
        outputs: Optional[List[str]] = None,
        members: Optional[List[str]] = None,
        node_id: Optional[str] = None,
        width: float = 230,
        height: float = 130,
    ) -> NodeItem:
        if node_id is None:
            node_id = f"N{self.node_counter}"
            self.node_counter += 1
        else:
            self.node_counter = max(self.node_counter, int(node_id[1:]) + 1)

        node = NodeItem(
            node_id=node_id,
            node_type=node_type,
            title=title,
            description=description,
            inputs=inputs,
            outputs=outputs,
            members=members,
            on_structure_changed=self.refresh_mermaid_preview,
            width=width,
            height=height,
        )
        self.nodes[node_id] = node
        self.scene.addItem(node)
        return node

    def add_edge(
        self,
        source: NodeItem,
        target: NodeItem,
        io_label: str = "",
        source_port: str = "",
        target_port: str = "",
    ) -> None:
        if source is target:
            return

        edge = EdgeItem(source, target, io_label=io_label, source_port=source_port, target_port=target_port)
        source.connected_edges.append(edge)
        target.connected_edges.append(edge)
        self.edges.append(edge)
        self.scene.addItem(edge)
        self.refresh_mermaid_preview()

    def connect_selected_nodes(self) -> None:
        if self.port_connect_mode:
            QMessageBox.information(self, "Port Mode", "Port connect mode is ON, click ports directly.")
            return

        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if len(selected_nodes) != 2:
            QMessageBox.warning(self, "Connect", "Select exactly 2 nodes.")
            return

        source, target = selected_nodes[0], selected_nodes[1]
        if not source.outputs:
            QMessageBox.warning(self, "Connect", "Source node has no output ports.")
            return
        if not target.inputs:
            QMessageBox.warning(self, "Connect", "Target node has no input ports.")
            return

        source_port, ok = QInputDialog.getItem(self, "Source Output", "Choose output:", source.outputs, editable=False)
        if not ok:
            return
        target_port, ok = QInputDialog.getItem(self, "Target Input", "Choose input:", target.inputs, editable=False)
        if not ok:
            return

        label = f"{source_port} -> {target_port}"
        self.add_edge(source, target, label, source_port, target_port)

    def nest_selected_nodes(self) -> None:
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if len(selected_nodes) != 2:
            QMessageBox.warning(self, "Nest", "Select child then parent (2 nodes).")
            return

        child, parent = selected_nodes[0], selected_nodes[1]
        if parent.has_ancestor(child):
            QMessageBox.warning(self, "Nest", "Invalid nesting: parent is a descendant of child.")
            return

        child.set_parent_node(parent)
        for edge in child.connected_edges:
            edge.update_path()
        self.refresh_mermaid_preview()

    def unnest_selected_nodes(self) -> None:
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if not selected_nodes:
            QMessageBox.warning(self, "Unnest", "Select at least one node.")
            return

        for node in selected_nodes:
            node.set_parent_node(None)
            for edge in node.connected_edges:
                edge.update_path()
        self.refresh_mermaid_preview()

    def delete_selected(self) -> None:
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        selected_edges = [item for item in self.scene.selectedItems() if isinstance(item, EdgeItem)]

        for edge in selected_edges:
            if edge in edge.source.connected_edges:
                edge.source.connected_edges.remove(edge)
            if edge in edge.target.connected_edges:
                edge.target.connected_edges.remove(edge)
            if edge in self.edges:
                self.edges.remove(edge)
            self.scene.removeItem(edge)

        for node in selected_nodes:
            related = [e for e in self.edges if e.source is node or e.target is node]
            for edge in related:
                if edge in edge.source.connected_edges:
                    edge.source.connected_edges.remove(edge)
                if edge in edge.target.connected_edges:
                    edge.target.connected_edges.remove(edge)
                if edge in self.edges:
                    self.edges.remove(edge)
                self.scene.removeItem(edge)

            if node.node_id in self.nodes:
                del self.nodes[node.node_id]
            self.scene.removeItem(node)

        self.refresh_mermaid_preview()

    def on_selection_changed(self) -> None:
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if len(selected_nodes) != 1:
            return

        node = selected_nodes[0]
        self.title_input.setText(node.title)
        self.type_input.setCurrentText(node.node_type)
        self.width_input.setValue(int(node.rect().width()))
        self.height_input.setValue(int(node.rect().height()))
        self.inputs_input.setPlainText("\n".join(node.inputs))
        self.outputs_input.setPlainText("\n".join(node.outputs))
        self.members_input.setPlainText("\n".join(node.members))
        self.description_input.setPlainText(node.description)

    @staticmethod
    def _parse_lines(text: str) -> List[str]:
        return [line.strip() for line in text.splitlines() if line.strip()]

    def apply_properties_to_selected(self) -> None:
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if not selected_nodes:
            QMessageBox.information(self, "Hint", "Select at least one node first.")
            return

        title = self.title_input.text().strip()
        node_type = self.type_input.currentText().strip()
        width = self.width_input.value()
        height = self.height_input.value()
        inputs = self._parse_lines(self.inputs_input.toPlainText())
        outputs = self._parse_lines(self.outputs_input.toPlainText())
        members = self._parse_lines(self.members_input.toPlainText())
        description = self.description_input.toPlainText().strip()

        for node in selected_nodes:
            node.title = title or node.title
            node.node_type = node_type or node.node_type
            node.inputs = inputs
            node.outputs = outputs
            node.members = members
            node.description = description
            node.set_size(width, height)
            node.refresh_style()
            node.refresh_texts()

        self.refresh_mermaid_preview()

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace('"', "'").replace("\n", "<br/>")

    def _node_mermaid_text(self, node: NodeItem) -> str:
        lines: List[str] = [self._escape(node.title)]

        desc = node.description.strip()
        if desc:
            lines.append(f"<sub>{self._escape(desc[:180] + ('...' if len(desc) > 180 else ''))}</sub>")
        if node.inputs:
            lines.append(f"<sub>IN: {self._escape(', '.join(node.inputs[:6]))}</sub>")
        if node.outputs:
            lines.append(f"<sub>OUT: {self._escape(', '.join(node.outputs[:6]))}</sub>")
        if node.members:
            lines.append(f"<sub>MEM: {self._escape(', '.join(node.members[:6]))}</sub>")

        return "<br/>".join(lines)

    def _node_line(self, node: NodeItem, indent: str = "") -> str:
        text = self._node_mermaid_text(node)
        nid = node.node_id
        shape = node.node_type
        if shape == "program":
            return f'{indent}{nid}(["{text}"])'
        if shape == "module":
            return f'{indent}{nid}[/"{text}"/]'
        if shape == "class":
            return f'{indent}{nid}[["{text}"]]'
        if shape == "struct":
            return f'{indent}{nid}[("{text}")]'
        if shape == "interface":
            return f'{indent}{nid}{{{{"{text}"}}}}'
        return f'{indent}{nid}["{text}"]'

    def _children_of(self, parent_id: Optional[str]) -> List[NodeItem]:
        children = [node for node in self.nodes.values() if node.parent_node_id == parent_id]
        children.sort(key=lambda x: x.node_id)
        return children

    def _render_node_tree(self, node: NodeItem, lines: List[str], indent: str = "") -> None:
        children = self._children_of(node.node_id)
        if not children:
            lines.append(self._node_line(node, indent))
            return

        lines.append(f'{indent}subgraph {node.node_id}_GROUP["{self._escape(node.title)}"]')
        lines.append(self._node_line(node, indent + "  "))
        for child in children:
            self._render_node_tree(child, lines, indent + "  ")
        lines.append(f"{indent}end")

    def generate_mermaid(self) -> str:
        lines: List[str] = ["flowchart LR"]

        roots = self._children_of(None)
        for root in roots:
            self._render_node_tree(root, lines, "  ")

        lines.append("")
        lines.append("  %% I/O Connections")
        for edge in self.edges:
            src = edge.source.node_id
            tgt = edge.target.node_id
            label = self._escape(edge.io_label.strip())
            if label:
                lines.append(f'  {src} --|"{label}"|--> {tgt}')
            else:
                lines.append(f"  {src} --> {tgt}")

        lines.append("")
        lines.append("  %% Style classes")
        for ntype, info in NODE_TEMPLATES.items():
            class_name = f"cls_{ntype}"
            color = info["color"]
            lines.append(f"  classDef {class_name} fill:{color}22,stroke:{color},stroke-width:2px;")
        for node in sorted(self.nodes.values(), key=lambda n: n.node_id):
            lines.append(f"  class {node.node_id} cls_{node.node_type};")

        lines.append("")
        lines.append("  %% VC_METADATA_BEGIN")
        for node in sorted(self.nodes.values(), key=lambda n: n.node_id):
            scene_pos = node.scenePos()
            payload = {
                "id": node.node_id,
                "type": node.node_type,
                "title": node.title,
                "description": node.description,
                "inputs": node.inputs,
                "outputs": node.outputs,
                "members": node.members,
                "x": round(scene_pos.x(), 2),
                "y": round(scene_pos.y(), 2),
                "w": round(node.rect().width(), 2),
                "h": round(node.rect().height(), 2),
                "parent": node.parent_node_id,
            }
            lines.append(f"  %% VC_NODE {json.dumps(payload, ensure_ascii=True)}")

        for edge in self.edges:
            payload = {
                "source": edge.source.node_id,
                "target": edge.target.node_id,
                "source_port": edge.source_port,
                "target_port": edge.target_port,
                "label": edge.io_label,
            }
            lines.append(f"  %% VC_EDGE {json.dumps(payload, ensure_ascii=True)}")

        lines.append("  %% VC_METADATA_END")
        return "\n".join(lines)

    def clear_graph(self) -> None:
        for edge in list(self.edges):
            self.scene.removeItem(edge)
        for node in list(self.nodes.values()):
            self.scene.removeItem(node)
        self.edges = []
        self.nodes = {}
        self.node_counter = 1

    def _load_with_metadata(self, content: str) -> bool:
        node_records: List[dict] = []
        edge_records: List[dict] = []

        for line in content.splitlines():
            s = line.strip()
            if s.startswith("%% VC_NODE "):
                node_records.append(json.loads(s[len("%% VC_NODE ") :]))
            elif s.startswith("%% VC_EDGE "):
                edge_records.append(json.loads(s[len("%% VC_EDGE ") :]))

        if not node_records:
            return False

        self.clear_graph()
        pending_parent: Dict[str, Optional[str]] = {}

        for rec in node_records:
            node = self.create_node(
                node_type=rec.get("type", "process"),
                title=rec.get("title", rec["id"]),
                description=rec.get("description", ""),
                inputs=rec.get("inputs", []),
                outputs=rec.get("outputs", []),
                members=rec.get("members", []),
                node_id=rec["id"],
                width=float(rec.get("w", 230)),
                height=float(rec.get("h", 130)),
            )
            node.setPos(float(rec.get("x", 0)), float(rec.get("y", 0)))
            pending_parent[node.node_id] = rec.get("parent")

        for node_id, parent_id in pending_parent.items():
            if not parent_id:
                continue
            child = self.nodes.get(node_id)
            parent = self.nodes.get(parent_id)
            if child is not None and parent is not None and not parent.has_ancestor(child):
                child.set_parent_node(parent)

        for rec in edge_records:
            source = self.nodes.get(rec.get("source", ""))
            target = self.nodes.get(rec.get("target", ""))
            if source is None or target is None:
                continue
            self.add_edge(
                source,
                target,
                io_label=rec.get("label", ""),
                source_port=rec.get("source_port", ""),
                target_port=rec.get("target_port", ""),
            )

        self.refresh_mermaid_preview()
        return True

    def _load_fallback(self, content: str) -> None:
        self.clear_graph()

        node_types: Dict[str, str] = {}
        edge_records: List[tuple[str, str, str]] = []

        class_pattern = re.compile(r"^\s*class\s+(N\d+)\s+cls_([a-zA-Z0-9_]+)")
        edge_pattern = re.compile(r'^\s*(N\d+)\s*--\|"(.*?)"\|-->\s*(N\d+)')
        simple_edge_pattern = re.compile(r"^\s*(N\d+)\s*-->\s*(N\d+)")

        for line in content.splitlines():
            m_class = class_pattern.search(line)
            if m_class:
                node_types[m_class.group(1)] = m_class.group(2)
                continue

            m_edge = edge_pattern.search(line)
            if m_edge:
                edge_records.append((m_edge.group(1), m_edge.group(3), m_edge.group(2)))
                continue

            m_simple = simple_edge_pattern.search(line)
            if m_simple:
                edge_records.append((m_simple.group(1), m_simple.group(2), ""))

        if not node_types:
            raise ValueError("No recoverable node definitions found")

        sorted_ids = sorted(node_types.keys(), key=lambda nid: int(nid[1:]))
        for idx, node_id in enumerate(sorted_ids):
            node = self.create_node(
                node_type=node_types[node_id],
                title=node_id,
                description="Imported without metadata; update details as needed",
                node_id=node_id,
            )
            node.setPos((idx % 4) * 320 - 460, (idx // 4) * 200 - 200)

        for src_id, tgt_id, label in edge_records:
            src = self.nodes.get(src_id)
            tgt = self.nodes.get(tgt_id)
            if src is None or tgt is None:
                continue
            self.add_edge(src, tgt, io_label=label)

        self.refresh_mermaid_preview()

    def import_mermaid_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Mermaid",
            "",
            "Mermaid Files (*.mmd *.txt);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            if not self._load_with_metadata(content):
                self._load_fallback(content)
                QMessageBox.information(
                    self,
                    "Imported (fallback mode)",
                    "No full metadata found. Imported using basic structure only.",
                )
            else:
                QMessageBox.information(self, "Import successful", "Nodes and edges restored with metadata.")
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", f"Cannot parse this file:\n{exc}")

    def export_mermaid_file(self) -> None:
        content = self.generate_mermaid()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Mermaid",
            "diagram.mmd",
            "Mermaid Files (*.mmd);;Text Files (*.txt)",
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        QMessageBox.information(self, "Export successful", f"Saved to:\n{path}")

    def refresh_mermaid_preview(self) -> None:
        self.mermaid_preview.setPlainText(self.generate_mermaid())


def run() -> int:
    app = QApplication.instance() or QApplication([])
    window = MermaidFlowEditor()
    window.show()
    return app.exec()
