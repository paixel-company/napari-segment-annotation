import napari
import requests
import numpy as np
from napari.layers import Labels
from napari_plugin_engine import napari_hook_implementation
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget, QComboBox, QPushButton

# Fetch label data from API and create id -> safe_name mapping
def fetch_label_data(template="ccfv3"):
    url = f"https://smart.siat.ac.cn/api/v1/atlas-structures/?format=json&template={template}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        # Check if 'id' is a digit string and ignore empty or invalid 'id'
        return {int(item["id"]): item["safe_name"] for item in data if item["id"].isdigit()}
    else:
        print("Failed to fetch label data")
        return {}

class MaskLabelViewer(QWidget):
    def __init__(self, viewer: napari.Viewer):
        super().__init__()
        self.viewer = viewer
        self.template = "ccfv3"  # Default template
        self.ID_TO_SAFE_NAME = fetch_label_data(self.template)  # Initial label data

        self.label_display = QLabel("Click 'Activate' and select a mask area to view label name")

        # Template selector
        self.template_selector = QComboBox()
        self.template_selector.addItems(["ccfv3", "civm_rhesus"])
        self.template_selector.currentIndexChanged.connect(self.update_template)

        # Layer selector
        self.layer_selector = QComboBox()
        self.update_layer_list()

        # Activate button
        self.activate_button = QPushButton("Activate")
        self.activate_button.clicked.connect(self.activate_click)

        # Layout settings
        layout = QVBoxLayout()
        layout.addWidget(self.label_display)
        layout.addWidget(self.template_selector)
        layout.addWidget(self.layer_selector)
        layout.addWidget(self.activate_button)
        self.setLayout(layout)

        # Variable initialization
        self.click_callback = self.on_click
        self.selected_layer = None
        self.is_active = False

    # Update template
    def update_template(self):
        self.template = self.template_selector.currentText()
        self.ID_TO_SAFE_NAME = fetch_label_data(self.template)  # Update label data
        self.label_display.setText(f"Template switched to {self.template}")

    # Update layer list
    def update_layer_list(self):
        self.layer_selector.clear()
        for layer in self.viewer.layers:
            if isinstance(layer, Labels):  # Only show Labels layers
                self.layer_selector.addItem(layer.name)

    # Activate click event
    def activate_click(self):
        self.is_active = True
        layer_name = self.layer_selector.currentText()
        if layer_name:
            self.selected_layer = self.viewer.layers[layer_name]
            self.add_click_callback(self.selected_layer)
        self.label_display.setText("Activated, click on the mask area to get the label name")

    # Add click event callback
    def add_click_callback(self, layer):
        if isinstance(layer, Labels):
            layer.mouse_drag_callbacks.append(self.click_callback)

    # Click event handler
    def on_click(self, layer, event):
        if self.is_active and event.button == 1:  # Active and left-click
            position = tuple(map(int, event.position))
            # Get the mask label value (id)
            mask_value = layer.data[position[:layer.ndim]]
                
            # Get the label name
            label_name = self.ID_TO_SAFE_NAME.get(mask_value, "Unknown label")
            self.label_display.setText(f"Mask value: {mask_value}, Label name: {label_name}")
            print(f"Picked mask value: {mask_value}, mapped to label name: {label_name}")
            self.is_active = False  # Deactivate after clicking

# Provide the widget function, returning an instance of MaskLabelViewer
@napari_hook_implementation
def napari_experimental_provide_dock_widget(viewer: napari.Viewer) -> QWidget:
    widget = MaskLabelViewer(viewer)
    viewer.layers.events.inserted.connect(widget.update_layer_list)  # Auto-update layer list
    return widget
