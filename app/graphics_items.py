from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from .templates import NODE_TEMPLATES


class EdgeItem(QGraphicsPathItem):
    def __init__(
        self,
        source: "NodeItem",
        target: "NodeItem",
        io_label: str = "",
        source_port: str = "",
        target_port: str = "",
    ) -> None:
        super().__init__()
        self.source = source
        self.target = target
        self.source_port = source_port
        self.target_port = target_port
        self.io_label = io_label
        self.label_item = QGraphicsSimpleTextItem(io_label, self)
        self.setZValue(-1)
        self.setFlag(QGraphicsPathItem.ItemIsSelectable, True)
        self.setPen(QPen(QColor("#444"), 2))
        self.update_path()

    def update_path(self) -> None:
        start = self.source.output_port_scene_pos(self.source_port)
        end = self.target.input_port_scene_pos(self.target_port)
        path = QPainterPath(start)

        dx = (end.x() - start.x()) * 0.5
        c1 = QPointF(start.x() + dx, start.y())
        c2 = QPointF(end.x() - dx, end.y())
        path.cubicTo(c1, c2, end)

        self.setPath(path)
        mid = path.pointAtPercent(0.5)
        self.label_item.setText(self.io_label)
        self.label_item.setPos(mid + QPointF(4, -14))


class NodeItem(QGraphicsRectItem):
    MIN_WIDTH = 140.0
    MIN_HEIGHT = 90.0
    HANDLE_SIZE = 12.0
    PORT_RADIUS = 4.0

    def __init__(
        self,
        node_id: str,
        node_type: str,
        title: str,
        description: str,
        inputs: Optional[List[str]] = None,
        outputs: Optional[List[str]] = None,
        members: Optional[List[str]] = None,
        on_structure_changed: Optional[Callable[[], None]] = None,
        width: float = 210,
        height: float = 120,
    ) -> None:
        super().__init__(0, 0, width, height)
        self.node_id = node_id
        self.node_type = node_type
        self.title = title
        self.description = description
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.members = members or []
        self.connected_edges: List[EdgeItem] = []
        self.parent_node_id: Optional[str] = None
        self.on_structure_changed = on_structure_changed
        self._is_resizing = False
        self._resize_start_scene = QPointF()
        self._resize_start_rect = QRectF()
        self.hovered_input_port: Optional[str] = None
        self.hovered_output_port: Optional[str] = None
        self.selected_output_port: Optional[str] = None

        self.setFlags(
            QGraphicsRectItem.ItemIsMovable
            | QGraphicsRectItem.ItemIsSelectable
            | QGraphicsRectItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        self.title_item = QGraphicsTextItem(self)
        self.body_item = QGraphicsTextItem(self)
        self.refresh_style()
        self.refresh_texts()

    def refresh_style(self) -> None:
        color = NODE_TEMPLATES.get(self.node_type, NODE_TEMPLATES["process"])["color"]
        fill = QColor(color)
        fill.setAlpha(48)
        self.setBrush(fill)
        self.setPen(QPen(QColor(color), 2))

    def refresh_texts(self) -> None:
        self.title_item.setDefaultTextColor(QColor("#111"))
        self.title_item.setFont(self.title_item.font())
        self.title_item.setPlainText(f"{self.node_type.upper()} | {self.title}")
        self.title_item.setPos(8, 6)

        parts: List[str] = []
        preview = self.description.strip().replace("\n", " ")
        if preview:
            parts.append(preview)
        if self.inputs:
            parts.append(f"IN: {', '.join(self.inputs)}")
        if self.outputs:
            parts.append(f"OUT: {', '.join(self.outputs)}")
        if self.members:
            parts.append(f"MEM: {', '.join(self.members)}")

        merged = "\n".join(parts)
        if len(merged) > 220:
            merged = merged[:217] + "..."

        self.body_item.setDefaultTextColor(QColor("#333"))
        self.body_item.setTextWidth(self.rect().width() - 16)
        self.body_item.setPlainText(merged)
        self.body_item.setPos(8, 34)

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemPositionHasChanged:
            for edge in self.connected_edges:
                edge.update_path()
        return super().itemChange(change, value)

    def paint(self, painter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None) -> None:
        super().paint(painter, option, widget)
        self._paint_ports(painter)
        handle = self._resize_handle_rect()
        painter.setBrush(QColor("#666" if self.isSelected() else "#999"))
        painter.setPen(QPen(QColor("#444"), 1))
        painter.drawRect(handle)

    def _port_anchor_y(self, index: int, count: int) -> float:
        if count <= 0:
            return self.rect().center().y()
        top = 48.0
        bottom = max(top + 1.0, self.rect().height() - 18.0)
        step = (bottom - top) / (count + 1)
        return top + step * (index + 1)

    def _paint_ports(self, painter) -> None:
        painter.setPen(QPen(QColor("#2a2a2a"), 1))

        for idx, name in enumerate(self.inputs):
            y = self._port_anchor_y(idx, len(self.inputs))
            x = self.rect().left()
            is_hover = name == self.hovered_input_port
            radius = self.PORT_RADIUS + (2.0 if is_hover else 0.0)
            painter.setBrush(QColor("#29a745") if is_hover else QColor("#2f7d32"))
            painter.drawEllipse(QPointF(x, y), radius, radius)
            painter.drawText(QPointF(x + 8, y + 4), name[:20])

        for idx, name in enumerate(self.outputs):
            y = self._port_anchor_y(idx, len(self.outputs))
            x = self.rect().right()
            is_hover = name == self.hovered_output_port
            is_selected_source = name == self.selected_output_port
            radius = self.PORT_RADIUS + (2.0 if (is_hover or is_selected_source) else 0.0)
            if is_selected_source:
                painter.setBrush(QColor("#ff8a3d"))
            elif is_hover:
                painter.setBrush(QColor("#e76f51"))
            else:
                painter.setBrush(QColor("#cf5c36"))
            painter.drawEllipse(QPointF(x, y), radius, radius)
            painter.drawText(QPointF(x - 110, y + 4), name[:20])

    def set_port_highlight(
        self,
        hovered_input_port: Optional[str] = None,
        hovered_output_port: Optional[str] = None,
        selected_output_port: Optional[str] = None,
    ) -> None:
        self.hovered_input_port = hovered_input_port
        self.hovered_output_port = hovered_output_port
        self.selected_output_port = selected_output_port
        self.update()

    def scene_center(self) -> QPointF:
        r = self.rect()
        return self.mapToScene(r.center())

    def input_port_scene_pos(self, port_name: str) -> QPointF:
        if port_name and port_name in self.inputs:
            idx = self.inputs.index(port_name)
            y = self._port_anchor_y(idx, len(self.inputs))
            return self.mapToScene(QPointF(self.rect().left(), y))
        return self.scene_center()

    def output_port_scene_pos(self, port_name: str) -> QPointF:
        if port_name and port_name in self.outputs:
            idx = self.outputs.index(port_name)
            y = self._port_anchor_y(idx, len(self.outputs))
            return self.mapToScene(QPointF(self.rect().right(), y))
        return self.scene_center()

    def _input_port_local_pos(self, name: str) -> Optional[QPointF]:
        if name not in self.inputs:
            return None
        idx = self.inputs.index(name)
        y = self._port_anchor_y(idx, len(self.inputs))
        return QPointF(self.rect().left(), y)

    def _output_port_local_pos(self, name: str) -> Optional[QPointF]:
        if name not in self.outputs:
            return None
        idx = self.outputs.index(name)
        y = self._port_anchor_y(idx, len(self.outputs))
        return QPointF(self.rect().right(), y)

    def input_port_hit_test(self, scene_pos: QPointF, tolerance: float = 8.0) -> Optional[str]:
        local_pos = self.mapFromScene(scene_pos)
        limit = tolerance * tolerance
        for name in self.inputs:
            pt = self._input_port_local_pos(name)
            if pt is None:
                continue
            dx = local_pos.x() - pt.x()
            dy = local_pos.y() - pt.y()
            if dx * dx + dy * dy <= limit:
                return name
        return None

    def output_port_hit_test(self, scene_pos: QPointF, tolerance: float = 8.0) -> Optional[str]:
        local_pos = self.mapFromScene(scene_pos)
        limit = tolerance * tolerance
        for name in self.outputs:
            pt = self._output_port_local_pos(name)
            if pt is None:
                continue
            dx = local_pos.x() - pt.x()
            dy = local_pos.y() - pt.y()
            if dx * dx + dy * dy <= limit:
                return name
        return None

    def _resize_handle_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.right() - self.HANDLE_SIZE,
            r.bottom() - self.HANDLE_SIZE,
            self.HANDLE_SIZE,
            self.HANDLE_SIZE,
        )

    def set_size(self, width: float, height: float) -> None:
        width = max(self.MIN_WIDTH, width)
        height = max(self.MIN_HEIGHT, height)
        self.prepareGeometryChange()
        self.setRect(0, 0, width, height)
        self.refresh_texts()
        for edge in self.connected_edges:
            edge.update_path()

    def set_parent_node(self, parent: Optional["NodeItem"]) -> None:
        if parent is None:
            scene_pos = self.mapToScene(QPointF(0, 0))
            self.setParentItem(None)
            self.setPos(scene_pos)
            self.parent_node_id = None
            for edge in self.connected_edges:
                edge.update_path()
            return

        if self is parent:
            return

        scene_pos = self.mapToScene(QPointF(0, 0))
        self.setParentItem(parent)
        self.setPos(parent.mapFromScene(scene_pos))
        self.parent_node_id = parent.node_id
        for edge in self.connected_edges:
            edge.update_path()

    def has_ancestor(self, maybe_ancestor: "NodeItem") -> bool:
        current = self.parentItem()
        while current is not None:
            if current is maybe_ancestor:
                return True
            current = current.parentItem()
        return False

    def _notify_structure_changed(self) -> None:
        if self.on_structure_changed:
            self.on_structure_changed()

    def _auto_parent_candidate(self) -> Optional["NodeItem"]:
        if self.scene() is None:
            return None

        center = self.scene_center()
        candidates: List[NodeItem] = []
        for item in self.scene().items(center):
            if not isinstance(item, NodeItem):
                continue
            if item is self:
                continue
            if item.has_ancestor(self):
                continue
            if item.sceneBoundingRect().contains(center):
                candidates.append(item)

        if not candidates:
            return None

        candidates.sort(key=lambda n: n.sceneBoundingRect().width() * n.sceneBoundingRect().height())
        return candidates[0]

    def hoverMoveEvent(self, event) -> None:
        if self._resize_handle_rect().contains(event.pos()):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._resize_handle_rect().contains(event.pos()):
            self._is_resizing = True
            self._resize_start_scene = event.scenePos()
            self._resize_start_rect = self.rect()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._is_resizing:
            delta = event.scenePos() - self._resize_start_scene
            self.set_size(
                self._resize_start_rect.width() + delta.x(),
                self._resize_start_rect.height() + delta.y(),
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._is_resizing:
            self._is_resizing = False
            self._notify_structure_changed()
            event.accept()
            return

        super().mouseReleaseEvent(event)

        candidate_parent = self._auto_parent_candidate()
        current_parent = self.parentItem()
        changed = False

        if candidate_parent is not None and candidate_parent is not current_parent:
            self.set_parent_node(candidate_parent)
            changed = True
        elif candidate_parent is None and current_parent is not None:
            parent_rect = current_parent.sceneBoundingRect()
            if not parent_rect.contains(self.scene_center()):
                self.set_parent_node(None)
                changed = True

        if changed:
            self._notify_structure_changed()
