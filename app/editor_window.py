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
        self.setWindowTitle("Vibe Coding Mermaid Flow Editor")
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
        self.scene.setSceneRect(-2400, -2400, 4800, 4800)
        self.scene.selectionChanged.connect(self.on_selection_changed)

        self.view = FlowGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.Antialiasing, True)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)

        self.template_list = QListWidget()
        self.template_list.setMinimumWidth(180)
        for key, data in NODE_TEMPLATES.items():
            item = QListWidgetItem(f"{data['label']} ({key})")
            item.setData(Qt.UserRole, key)
            self.template_list.addItem(item)
        self.template_list.itemDoubleClicked.connect(self.add_node_from_template)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("模板框（双击添加）"))
        left_layout.addWidget(QLabel("拖拽节点右下角可改大小；拖到其它节点内部可自动嵌套"))
        left_layout.addWidget(self.template_list)
        self.btn_add = QPushButton("添加选中模板")
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
        preview_dock = QDockWidget("Mermaid 预览", self)
        preview_dock.setWidget(self.mermaid_preview)
        self.addDockWidget(Qt.BottomDockWidgetArea, preview_dock)

        self._seed_example()
        self.refresh_mermaid_preview()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        self.addToolBar(toolbar)

        self.act_port_mode = QAction("端口连线模式", self)
        self.act_port_mode.setCheckable(True)
        self.act_port_mode.toggled.connect(self.toggle_port_connect_mode)
        toolbar.addAction(self.act_port_mode)

        act_connect = QAction("连接两个选中节点", self)
        act_connect.triggered.connect(self.connect_selected_nodes)
        toolbar.addAction(act_connect)

        act_nest = QAction("嵌套（子 -> 父）", self)
        act_nest.triggered.connect(self.nest_selected_nodes)
        toolbar.addAction(act_nest)

        act_unnest = QAction("取消嵌套", self)
        act_unnest.triggered.connect(self.unnest_selected_nodes)
        toolbar.addAction(act_unnest)

        act_delete = QAction("删除选中", self)
        act_delete.triggered.connect(self.delete_selected)
        toolbar.addAction(act_delete)

        act_export = QAction("导出 .mmd", self)
        act_export.triggered.connect(self.export_mermaid_file)
        toolbar.addAction(act_export)

        act_import = QAction("导入 .mmd", self)
        act_import.triggered.connect(self.import_mermaid_file)
        toolbar.addAction(act_import)

    def toggle_port_connect_mode(self, enabled: bool) -> None:
        self.port_connect_mode = enabled
        self.pending_source_port = None
        self.hovered_input_port = None
        self.hovered_output_port = None
        self.preview_scene_pos = None
        self._update_port_highlights()
        self.view.viewport().update()
        if enabled:
            self.statusBar().showMessage("端口连线模式已开启：先点输出端口，再点目标输入端口。", 5000)
        else:
            self.statusBar().showMessage("端口连线模式已关闭。", 3000)

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

            node.set_port_highlight(
                hovered_input_port=hover_input,
                hovered_output_port=hover_output,
                selected_output_port=selected_output,
            )

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
                self.statusBar().showMessage(
                    f"已选择源输出端口: {node.node_id}.{output_name}，请点击目标输入端口。",
                    6000,
                )
                return True
            self.statusBar().showMessage("请先点击一个输出端口作为连线起点。", 3500)
            return True

        source_node, source_port = self.pending_source_port

        if output_name:
            self.pending_source_port = (node, output_name)
            self._update_port_highlights()
            self.view.viewport().update()
            self.statusBar().showMessage(
                f"已切换源输出端口: {node.node_id}.{output_name}，请点击目标输入端口。",
                6000,
            )
            return True

        if not input_name:
            self.statusBar().showMessage("请点击目标节点的输入端口完成连线。", 3500)
            return True

        if source_node is node:
            self.statusBar().showMessage("不允许同一节点内部端口自连。", 3500)
            return True

        label = f"{source_port} -> {input_name}"
        self.add_edge(
            source_node,
            node,
            io_label=label,
            source_port=source_port,
            target_port=input_name,
        )
        self.pending_source_port = None
        self._update_port_highlights()
        self.view.viewport().update()
        self.statusBar().showMessage("端口连线已创建。", 2500)
        return True

    def _build_property_dock(self) -> None:
        self.title_input = QLineEdit()
        self.type_input = QComboBox()
        self.type_input.addItems(NODE_TEMPLATES.keys())

        self.width_input = QSpinBox()
        self.width_input.setRange(140, 2000)
        self.width_input.setValue(210)

        self.height_input = QSpinBox()
        self.height_input.setRange(90, 1500)
        self.height_input.setValue(120)

        self.inputs_input = QTextEdit()
        self.inputs_input.setPlaceholderText("每行一个输入，如: user_query")

        self.outputs_input = QTextEdit()
        self.outputs_input.setPlaceholderText("每行一个输出，如: normalized_prompt")

        self.members_input = QTextEdit()
        self.members_input.setPlaceholderText("每行一个成员变量，如: cache_store")

        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("用自然语言描述此框的行为、输入输出、约束、异常处理等")
        self.btn_apply = QPushButton("应用到选中节点")
        self.btn_apply.clicked.connect(self.apply_properties_to_selected)

        panel = QWidget()
        layout = QFormLayout(panel)
        layout.addRow("标题", self.title_input)
        layout.addRow("类型", self.type_input)
        layout.addRow("宽度", self.width_input)
        layout.addRow("高度", self.height_input)
        layout.addRow("输入", self.inputs_input)
        layout.addRow("输出", self.outputs_input)
        layout.addRow("成员变量", self.members_input)
        layout.addRow("描述", self.description_input)
        layout.addRow(self.btn_apply)

        dock = QDockWidget("节点属性", self)
        dock.setWidget(panel)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _seed_example(self) -> None:
        n1 = self.create_node(
            "program",
            "Prompt Orchestrator",
            "协调提示词生成流程，汇总上下文输入。",
            inputs=["raw_requirement", "session_context"],
            outputs=["brief"],
            members=["global_rules"],
        )
        n1.setPos(-300, -120)

        n2 = self.create_node(
            "class",
            "PromptTemplateEngine",
            "将自然语言约束整理为统一模板并输出规范化文本。",
            inputs=["brief"],
            outputs=["normalized_payload"],
            members=["template_registry", "style_rules"],
        )
        n2.setPos(80, -120)

        n3 = self.create_node(
            "function",
            "compile_prompt",
            "输入：需求描述。输出：Mermaid节点行为草稿。",
            inputs=["normalized_payload"],
            outputs=["mermaid_draft"],
        )
        n3.setPos(430, 80)

        self.add_edge(n1, n2, "brief -> brief", source_port="brief", target_port="brief")
        self.add_edge(
            n2,
            n3,
            "normalized_payload -> normalized_payload",
            source_port="normalized_payload",
            target_port="normalized_payload",
        )

    def add_selected_template(self) -> None:
        current = self.template_list.currentItem()
        if current is None:
            QMessageBox.information(self, "提示", "请先在左侧模板列表中选中一个模板。")
            return
        self.add_node_from_template(current)

    def add_node_from_template(self, item: QListWidgetItem) -> None:
        node_type = item.data(Qt.UserRole)
        title, ok = QInputDialog.getText(self, "新增模板节点", "节点标题：", text=f"New {node_type}")
        if not ok:
            return
        description, ok = QInputDialog.getMultiLineText(
            self,
            "新增模板节点",
            "节点行为描述（自然语言）：",
            "输入/输出、职责、边界条件...",
        )
        if not ok:
            return

        default_inputs = {
            "program": ["user_goal"],
            "class": ["state", "request"],
            "struct": ["field_name"],
            "function": ["input_arg"],
        }.get(node_type, [])
        default_outputs = {
            "program": ["workflow_output"],
            "class": ["service_result"],
            "struct": ["serialized_object"],
            "function": ["return_value"],
        }.get(node_type, [])

        node = self.create_node(
            node_type,
            title.strip() or f"New {node_type}",
            description.strip(),
            inputs=default_inputs,
            outputs=default_outputs,
        )
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
        width: float = 210,
        height: float = 120,
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
        edge = EdgeItem(
            source,
            target,
            io_label=io_label,
            source_port=source_port,
            target_port=target_port,
        )
        source.connected_edges.append(edge)
        target.connected_edges.append(edge)
        self.edges.append(edge)
        self.scene.addItem(edge)
        self.refresh_mermaid_preview()

    def connect_selected_nodes(self) -> None:
        if self.port_connect_mode:
            QMessageBox.information(
                self,
                "端口连线模式",
                "当前已开启端口连线模式。\n请在画布中直接点击输出端口，再点击输入端口完成连线。",
            )
            return

        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if len(selected_nodes) != 2:
            QMessageBox.warning(self, "连接节点", "请选择 2 个节点再执行连接。")
            return

        node_options = [f"{node.node_id} | {node.title}" for node in selected_nodes]
        source_text, ok = QInputDialog.getItem(
            self,
            "选择源节点",
            "请选择输出方节点：",
            node_options,
            editable=False,
        )
        if not ok:
            return

        source_index = node_options.index(source_text)
        source = selected_nodes[source_index]
        target = selected_nodes[1 - source_index]

        if not source.outputs:
            QMessageBox.warning(self, "连接节点", "源节点没有定义输出端口，请先在右侧属性中添加输出。")
            return
        if not target.inputs:
            QMessageBox.warning(self, "连接节点", "目标节点没有定义输入端口，请先在右侧属性中添加输入。")
            return

        source_port, ok = QInputDialog.getItem(
            self,
            "选择输出端口",
            f"{source.title} 的输出端口：",
            source.outputs,
            editable=False,
        )
        if not ok:
            return

        target_port, ok = QInputDialog.getItem(
            self,
            "选择输入端口",
            f"{target.title} 的输入端口：",
            target.inputs,
            editable=False,
        )
        if not ok:
            return

        default_label = f"{source_port} -> {target_port}"
        label, ok = QInputDialog.getText(self, "连接标签", "连接标签（可选）：", text=default_label)
        if not ok:
            return

        edge_label = label.strip() or default_label
        self.add_edge(
            source,
            target,
            io_label=edge_label,
            source_port=source_port,
            target_port=target_port,
        )

    def nest_selected_nodes(self) -> None:
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if len(selected_nodes) != 2:
            QMessageBox.warning(self, "嵌套节点", "请选择 2 个节点：先选子节点，再选父节点。")
            return

        child, parent = selected_nodes[0], selected_nodes[1]
        if parent.has_ancestor(child):
            QMessageBox.warning(self, "嵌套节点", "非法嵌套：父节点不能是子节点的后代。")
            return
        child.set_parent_node(parent)
        for edge in child.connected_edges:
            edge.update_path()
        self.refresh_mermaid_preview()

    def unnest_selected_nodes(self) -> None:
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        if not selected_nodes:
            QMessageBox.warning(self, "取消嵌套", "请至少选中 1 个节点。")
            return
        for node in selected_nodes:
            node.set_parent_node(None)
            for edge in node.connected_edges:
                edge.update_path()
        self.refresh_mermaid_preview()

    def delete_selected(self) -> None:
        selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        selected_edges = [item for item in self.scene.selectedItems() if isinstance(item, EdgeItem)]
        if not selected_nodes and not selected_edges:
            return

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
            QMessageBox.information(self, "提示", "请先选中至少一个节点。")
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
            return f"{indent}{nid}([\"{text}\"])"
        if shape == "module":
            return f"{indent}{nid}[/\"{text}\"/]"
        if shape == "class":
            return f"{indent}{nid}[[\"{text}\"]]"
        if shape == "struct":
            return f"{indent}{nid}[(\"{text}\")]"
        if shape == "interface":
            return f"{indent}{nid}{{{{\"{text}\"}}}}"
        return f"{indent}{nid}[\"{text}\"]"

    def _children_of(self, parent_id: Optional[str]) -> List[NodeItem]:
        children = [node for node in self.nodes.values() if node.parent_node_id == parent_id]
        children.sort(key=lambda x: x.node_id)
        return children

    def _render_node_tree(self, node: NodeItem, lines: List[str], indent: str = "") -> None:
        children = self._children_of(node.node_id)
        if not children:
            lines.append(self._node_line(node, indent))
            return

        group_label = self._escape(node.title)
        lines.append(f"{indent}subgraph {node.node_id}_GROUP[\"{group_label}\"]")
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
            if not label and edge.source_port and edge.target_port:
                label = self._escape(f"{edge.source_port} -> {edge.target_port}")
            if label:
                lines.append(f"  {src} --|\"{label}\"|--> {tgt}")
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
            node_payload = {
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
            lines.append(f"  %% VC_NODE {json.dumps(node_payload, ensure_ascii=True)}")

        for edge in self.edges:
            edge_payload = {
                "source": edge.source.node_id,
                "target": edge.target.node_id,
                "source_port": edge.source_port,
                "target_port": edge.target_port,
                "label": edge.io_label,
            }
            lines.append(f"  %% VC_EDGE {json.dumps(edge_payload, ensure_ascii=True)}")
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

    @staticmethod
    def _strip_html_label(raw: str) -> str:
        text = raw.replace("<br/>", "\n")
        text = re.sub(r"<sub>(.*?)</sub>", r"\n\1", text)
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()

    def _load_with_metadata(self, content: str) -> bool:
        node_records: List[dict] = []
        edge_records: List[dict] = []

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("%% VC_NODE "):
                payload = stripped[len("%% VC_NODE ") :]
                node_records.append(json.loads(payload))
            elif stripped.startswith("%% VC_EDGE "):
                payload = stripped[len("%% VC_EDGE ") :]
                edge_records.append(json.loads(payload))

        if not node_records:
            return False

        self.clear_graph()
        pending_parent: Dict[str, Optional[str]] = {}

        for record in node_records:
            node = self.create_node(
                node_type=record.get("type", "process"),
                title=record.get("title", record["id"]),
                description=record.get("description", ""),
                inputs=record.get("inputs", []),
                outputs=record.get("outputs", []),
                members=record.get("members", []),
                node_id=record["id"],
                width=float(record.get("w", 210)),
                height=float(record.get("h", 120)),
            )
            node.setPos(float(record.get("x", 0)), float(record.get("y", 0)))
            pending_parent[node.node_id] = record.get("parent")

        for node_id, parent_id in pending_parent.items():
            if not parent_id:
                continue
            child = self.nodes.get(node_id)
            parent = self.nodes.get(parent_id)
            if child is not None and parent is not None and not parent.has_ancestor(child):
                child.set_parent_node(parent)

        for record in edge_records:
            source = self.nodes.get(record.get("source", ""))
            target = self.nodes.get(record.get("target", ""))
            if source is None or target is None:
                continue
            self.add_edge(
                source,
                target,
                io_label=record.get("label", ""),
                source_port=record.get("source_port", ""),
                target_port=record.get("target_port", ""),
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
            raise ValueError("未检测到可恢复的节点定义。")

        sorted_ids = sorted(node_types.keys(), key=lambda nid: int(nid[1:]))
        for idx, node_id in enumerate(sorted_ids):
            node = self.create_node(
                node_type=node_types[node_id],
                title=node_id,
                description="从无元数据 mmd 导入，建议重新补充节点详情。",
                node_id=node_id,
            )
            node.setPos((idx % 4) * 280 - 420, (idx // 4) * 180 - 180)

        for src_id, tgt_id, label in edge_records:
            src = self.nodes.get(src_id)
            tgt = self.nodes.get(tgt_id)
            if src is None or tgt is None:
                continue
            self.add_edge(src, tgt, io_label=label)

        self.refresh_mermaid_preview()

    def import_mermaid_file(self) -> None:
        input_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入 Mermaid 文件",
            "",
            "Mermaid Files (*.mmd *.txt);;All Files (*)",
        )
        if not input_path:
            return

        try:
            with open(input_path, "r", encoding="utf-8") as file_obj:
                content = file_obj.read()

            if not self._load_with_metadata(content):
                self._load_fallback(content)
                QMessageBox.information(
                    self,
                    "导入完成（兼容模式）",
                    "该 mmd 文件未包含布局元数据，已按基础结构导入。\n"
                    "你可以调整节点后重新导出，后续即可完整恢复布局。",
                )
            else:
                QMessageBox.information(self, "导入成功", "已完整恢复节点、连线、端口与布局。")
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", f"无法解析该文件：\n{exc}")

    def refresh_mermaid_preview(self) -> None:
        self.mermaid_preview.setPlainText(self.generate_mermaid())

    def export_mermaid_file(self) -> None:
        content = self.generate_mermaid()
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 Mermaid 文件",
            "diagram.mmd",
            "Mermaid Files (*.mmd);;Text Files (*.txt)",
        )
        if not output_path:
            return

        with open(output_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(content)

        QMessageBox.information(self, "导出成功", f"已导出到：\n{output_path}")


def run() -> int:
    app = QApplication.instance() or QApplication([])
    window = MermaidFlowEditor()
    window.show()
    return app.exec()
