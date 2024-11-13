import napari
import requests
import numpy as np
from napari.layers import Labels
from napari_plugin_engine import napari_hook_implementation
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget, QComboBox, QPushButton

# 从接口加载标签数据并创建 id -> safe_name 的映射
def fetch_label_data(template="ccfv3"):
    url = f"https://smart.siat.ac.cn/api/v1/atlas-structures/?format=json&template={template}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        # 检查 'id' 字段是否是数字字符串，并忽略空字符串或无效的 'id'
        return {int(item["id"]): item["safe_name"] for item in data if item["id"].isdigit()}
    else:
        print("Failed to fetch label data")
        return {}

class MaskLabelViewer(QWidget):
    def __init__(self, viewer: napari.Viewer):
        super().__init__()
        self.viewer = viewer
        self.template = "ccfv3"  # 默认模板
        self.ID_TO_SAFE_NAME = fetch_label_data(self.template)  # 初始标签数据

        self.label_display = QLabel("点击 '激活' 后选择 mask 区域查看标签名称")

        # 模板选择器
        self.template_selector = QComboBox()
        self.template_selector.addItems(["ccfv3", "civm_rhesus"])
        self.template_selector.currentIndexChanged.connect(self.update_template)

        # 图层选择器
        self.layer_selector = QComboBox()
        self.update_layer_list()

        # 激活按钮
        self.activate_button = QPushButton("激活")
        self.activate_button.clicked.connect(self.activate_click)

        # 布局设置
        layout = QVBoxLayout()
        layout.addWidget(self.label_display)
        layout.addWidget(self.template_selector)
        layout.addWidget(self.layer_selector)
        layout.addWidget(self.activate_button)
        self.setLayout(layout)

        # 变量初始化
        self.click_callback = self.on_click
        self.selected_layer = None
        self.is_active = False

    # 更新模板
    def update_template(self):
        self.template = self.template_selector.currentText()
        self.ID_TO_SAFE_NAME = fetch_label_data(self.template)  # 更新标签数据
        self.label_display.setText(f"模板已切换为 {self.template}")

    # 更新图层列表
    def update_layer_list(self):
        self.layer_selector.clear()
        for layer in self.viewer.layers:
            if isinstance(layer, Labels):  # 只显示 Labels 类型的层
                self.layer_selector.addItem(layer.name)

    # 激活点击事件
    def activate_click(self):
        self.is_active = True
        layer_name = self.layer_selector.currentText()
        if layer_name:
            self.selected_layer = self.viewer.layers[layer_name]
            self.add_click_callback(self.selected_layer)
        self.label_display.setText("已激活，请点击 mask 区域以获取标签名称")

    # 添加点击事件回调函数
    def add_click_callback(self, layer):
        if isinstance(layer, Labels):
            layer.mouse_drag_callbacks.append(self.click_callback)

    # 点击事件处理函数
    def on_click(self, layer, event):
        if self.is_active and event.button == 1:  # 激活状态并且左键点击
            position = tuple(map(int, event.position))
            # 获取 mask 的标签值（id）
            mask_value = layer.data[position[:layer.ndim]]
                
            # 获取标签名称
            label_name = self.ID_TO_SAFE_NAME.get(mask_value, "未知标签")
            self.label_display.setText(f"Mask值: {mask_value}, 标签名称: {label_name}")
            print(f"Picked mask value: {mask_value}, mapped to label name: {label_name}")
            self.is_active = False  # 点击完成后自动取消激活状态

# 提供小部件的函数，返回 MaskLabelViewer 实例
@napari_hook_implementation
def napari_experimental_provide_dock_widget(viewer: napari.Viewer) -> QWidget:
    widget = MaskLabelViewer(viewer)
    viewer.layers.events.inserted.connect(widget.update_layer_list)  # 自动更新图层列表
    return widget
