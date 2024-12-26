import napari
from napari_plugin_engine import napari_hook_implementation
from qtpy.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QLabel,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QHBoxLayout,
    QToolTip,
)
import requests
from PyQt5.QtCore import Qt
from napari.layers import Labels


class LabelFilter(QWidget):
    def __init__(self, viewer: napari.Viewer):
        super().__init__()
        self.viewer = viewer

        # 数据相关变量
        self.full_data = {}  # 全量数据 (id -> safe_name)
        self.filtered_data = {}  # 过滤后的数据
        self.page_size = 20  # 每页显示多少条数据
        self.current_page = 1  # 当前页

        # 初始化 UI 组件
        self.label_display = QLabel("Select a template and search for labels:")
        self.template_selector = QComboBox()
        self.template_selector.addItems(["ccfv3", "civm_rhesus", "visor"])
        self.template_selector.currentIndexChanged.connect(self.update_template)

        self.layer_selector = QComboBox()
        self.update_layer_list()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Label ID or Safe Name")
        self.search_input.textChanged.connect(self.apply_search)

        # 分页控件
        self.page_info = QLabel(f"Page {self.current_page}")
        self.previous_button = QPushButton("Previous")
        self.previous_button.clicked.connect(self.go_to_previous_page)
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.go_to_next_page)

        # Label 数据表格
        self.label_table = QTableWidget()
        self.label_table.setColumnCount(2)
        self.label_table.setHorizontalHeaderLabels(["Label ID", "Safe Name"])
        self.label_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.label_table.setMouseTracking(True)  # 启用鼠标跟踪
        self.label_table.cellEntered.connect(self.show_tooltip)  # 连接鼠标悬停事件

        # 布局
        pagination_layout = QHBoxLayout()
        pagination_layout.addWidget(self.previous_button)
        pagination_layout.addWidget(self.page_info)
        pagination_layout.addWidget(self.next_button)

        layout = QVBoxLayout()
        layout.addWidget(self.label_display)
        layout.addWidget(QLabel("Select Template:"))
        layout.addWidget(self.template_selector)
        layout.addWidget(QLabel("Select Layer:"))
        layout.addWidget(self.layer_selector)
        layout.addWidget(QLabel("Search:"))  # 添加搜索标签
        layout.addWidget(self.search_input)  # 添加搜索输入框
        layout.addWidget(self.label_table)
        layout.addLayout(pagination_layout)
        self.setLayout(layout)

        # 初始加载数据
        self.update_template()

    def fetch_label_data(self, template="ccfv3"):
        """从接口获取所有 Label 数据"""
        url = f"https://smart.siat.ac.cn/api/v1/atlas-structures/?format=json&template={template}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                return {int(item["id"]): item["safe_name"] for item in data if item["id"].isdigit()}
            else:
                print(f"Failed to fetch label data, status code: {response.status_code}")
                return {}
        except Exception as e:
            print(f"Error fetching label data: {str(e)}")
            return {}

    def update_template(self):
        """更新模板数据"""
        self.template = self.template_selector.currentText()
        self.full_data = self.fetch_label_data(self.template)
        self.filtered_data = self.full_data
        self.current_page = 1
        self.update_pagination()

    def update_layer_list(self):
        """更新图层列表，仅显示 Labels 图层"""
        self.layer_selector.clear()
        for layer in self.viewer.layers:
            if isinstance(layer, Labels):
                self.layer_selector.addItem(layer.name)

    def apply_search(self):
        """根据搜索关键词更新数据"""
        query = self.search_input.text().lower()
        if query:
            self.filtered_data = {
                label_id: name
                for label_id, name in self.full_data.items()
                if query in str(label_id) or query in name.lower()
            }
        else:
            self.filtered_data = self.full_data
        self.current_page = 1
        self.update_pagination()

    def update_pagination(self):
        """更新分页显示"""
        # 计算分页数据
        start_index = (self.current_page - 1) * self.page_size
        end_index = start_index + self.page_size
        items = list(self.filtered_data.items())
        current_page_data = dict(items[start_index:end_index])

        # 更新表格显示
        self.label_table.setRowCount(len(current_page_data))
        for row, (label_id, safe_name) in enumerate(current_page_data.items()):
            self.label_table.setItem(row, 0, QTableWidgetItem(str(label_id)))
            self.label_table.setItem(row, 1, QTableWidgetItem(safe_name))

        # 更新分页信息
        total_pages = (len(self.filtered_data) + self.page_size - 1) // self.page_size
        self.page_info.setText(f"Page {self.current_page} of {total_pages}")

        # 控制按钮可用性
        self.previous_button.setEnabled(self.current_page > 1)
        self.next_button.setEnabled(self.current_page < total_pages)

    def go_to_previous_page(self):
        """跳转到上一页"""
        if self.current_page > 1:
            self.current_page -= 1
            self.update_pagination()

    def go_to_next_page(self):
        """跳转到下一页"""
        total_pages = (len(self.filtered_data) + self.page_size - 1) // self.page_size
        if self.current_page < total_pages:
            self.current_page += 1
            self.update_pagination()

    def show_tooltip(self, row, column):
        """鼠标悬停时显示完整文本"""
        if column == 1:  # 仅对第二列 (Safe Name) 显示 Tooltip
            item = self.label_table.item(row, column)
            if item:
                QToolTip.showText(
                    self.label_table.viewport().mapToGlobal(self.label_table.visualItemRect(item).topLeft()),
                    item.text(),
                    self.label_table,
                )


# 提供插件小部件
@napari_hook_implementation
def napari_experimental_provide_dock_widget(viewer: napari.Viewer) -> QWidget:
    widget = LabelFilter(viewer)
    viewer.layers.events.inserted.connect(widget.update_layer_list)  # 自动更新图层列表
    return widget