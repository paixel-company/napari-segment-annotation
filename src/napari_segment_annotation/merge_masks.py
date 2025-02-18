import numpy as np
from napari.types import LabelsData
from magicgui import magic_factory
from napari_plugin_engine import napari_hook_implementation
from napari.layers import Labels
from pathlib import Path
from skimage.io import imread

@magic_factory(call_button="Merge Masks", viewer={'bind': 'viewer'})  # 绑定 viewer 参数
def merge_masks(viewer, base_mask_layer: Labels, overlay_mask_layer: Labels) -> None:
    """将叠加mask中的非零区域覆盖到基础mask中。"""
    if base_mask_layer is None or overlay_mask_layer is None:
        print("Please select both base mask and overlay mask layers.")
        return

    # 获取两个 mask 的数据
    base_mask_data = base_mask_layer.data
    overlay_mask_data = overlay_mask_layer.data

    # 确保两个 mask 的形状一致
    if base_mask_data.shape != overlay_mask_data.shape:
        print("Masks have different shapes!")
        return

    # 合并两个 mask：非零区域覆盖
    base_mask_data[overlay_mask_data != 0] = overlay_mask_data[overlay_mask_data != 0]

    # 将合并后的数据赋回基础mask图层
    base_mask_layer.data = base_mask_data

    # 强制刷新显示
    base_mask_layer.refresh()  # 强制刷新显示以更新图层

# 注册插件面板，返回插件而非按钮
@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    """返回自定义的插件面板，并在面板中显示合并操作"""
    return [merge_masks]  # 返回插件而非按钮
