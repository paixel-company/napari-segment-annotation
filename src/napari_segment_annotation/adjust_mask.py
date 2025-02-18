import numpy as np
from napari.types import LabelsData
from skimage.io import imread, imsave
from magicgui import magic_factory
from napari_plugin_engine import napari_hook_implementation
from pathlib import Path

@magic_factory(call_button="Load Mask")
def load_mask(mask_path: Path) -> LabelsData:
    """读取mask文件并返回Labels层数据。"""
    mask = imread(str(mask_path))
    return mask

@magic_factory(
    call_button="Adjust and Save Mask",
    operation={"choices": ["invert", "threshold", "none"]},
    threshold_value={"label": "Threshold Value", "min": 0, "max": 65535, "step": 1},
    save_path={"label": "Save Adjusted Mask As", "mode": "w", "filter": "*.tif;*.tiff"}
)
def adjust_mask(
    mask_layer: 'napari.layers.Labels',
    operation: str = 'none',
    threshold_value: float = 0,  # 阈值
    save_path: Path = None
) -> None:
    """根据选择的操作调整mask，并保存到文件。"""
    if mask_layer is None:
        print("Please select a mask layer.")
        return

    # 根据选择的操作进行调整
    if operation == 'invert':
        adjusted_mask = np.max(mask_layer.data) - mask_layer.data  # 反转mask
    elif operation == 'threshold':
        # 只保留等于阈值的部分，其他设为 0
        adjusted_mask = np.copy(mask_layer.data)
        adjusted_mask[adjusted_mask != threshold_value] = 0  # 仅保留等于阈值的部分
    else:
        adjusted_mask = mask_layer.data  # 不做任何操作

    mask_layer.data = adjusted_mask

    # 强制刷新显示
    mask_layer.refresh()  # 强制刷新显示以更新图层

    # 如果指定了保存路径，则将调整后的mask保存到文件
    if save_path is not None:
        try:
            imsave(str(save_path), adjusted_mask.astype(np.uint16))
            print(f"Adjusted mask saved to {save_path}")
        except Exception as e:
            print(f"Error saving mask: {e}")


# 注册插件面板
@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    return [load_mask, adjust_mask]  # 注册所有按钮