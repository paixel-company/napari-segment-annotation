import napari
from napari_plugin_engine import napari_hook_implementation
from qtpy.QtWidgets import QVBoxLayout, QWidget, QLabel, QComboBox, QSpinBox, QPushButton
from napari.layers import Labels

class LabelValueSetter(QWidget):
    def __init__(self, viewer: napari.Viewer):
        super().__init__()
        self.viewer = viewer

        # 初始化UI组件
        self.label_display = QLabel("Select a layer and set a label value for the brush")

        # 图层选择器
        self.layer_selector = QComboBox()
        self.update_layer_list()

        # Label值设置器
        self.label_value_selector = QSpinBox()
        self.label_value_selector.setRange(0, 9999)  # 根据需求调整范围
        self.label_value_selector.setValue(1)

        # 应用按钮
        self.apply_button = QPushButton("Apply Label Value")
        self.apply_button.clicked.connect(self.apply_label_value)

        # 刷新图层列表按钮
        self.refresh_button = QPushButton("Refresh Layers")
        self.refresh_button.clicked.connect(self.update_layer_list)

        # 布局设置
        layout = QVBoxLayout()
        layout.addWidget(self.label_display)
        layout.addWidget(self.layer_selector)
        layout.addWidget(QLabel("Brush Label Value:"))
        layout.addWidget(self.label_value_selector)
        layout.addWidget(self.apply_button)
        layout.addWidget(self.refresh_button)
        self.setLayout(layout)

    # 更新图层列表
    def update_layer_list(self):
        self.layer_selector.clear()
        for layer in self.viewer.layers:
            if isinstance(layer, Labels):  # 仅列出 Labels 图层
                self.layer_selector.addItem(layer.name)

    # 设置 Label 值
    def apply_label_value(self):
        layer_name = self.layer_selector.currentText()
        label_value = self.label_value_selector.value()

        if layer_name:
            selected_layer = self.viewer.layers[layer_name]
            if isinstance(selected_layer, Labels):
                selected_layer.brush_value = label_value  # 设置笔刷标注值
                self.label_display.setText(f"Set brush label value to {label_value} on layer '{layer_name}'")
            else:
                self.label_display.setText(f"Selected layer '{layer_name}' is not a Labels layer.")
        else:
            self.label_display.setText("No layer selected.")

# 提供插件小部件
@napari_hook_implementation
def napari_experimental_provide_dock_widget(viewer: napari.Viewer) -> QWidget:
    widget = LabelValueSetter(viewer)
    viewer.layers.events.inserted.connect(widget.update_layer_list)  # 自动更新图层列表
    return widget