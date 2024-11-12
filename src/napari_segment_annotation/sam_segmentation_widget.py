import os
import urllib.request
import numpy as np
import dask.array as da
import napari
from magicgui import magic_factory
from napari.layers import Image, Points, Labels
from segment_anything import sam_model_registry, SamPredictor
import torch

def download_default_checkpoint(model_type, save_dir):
    """
    下载默认的 SAM 模型检查点文件。
    """
    model_urls = {
        "vit_b": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth",
        "vit_l": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_l_0b3195.pth",
        "vit_h": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth",
    }

    url = model_urls.get(model_type)
    if not url:
        raise ValueError(f"不支持的模型类型：{model_type}")

    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, os.path.basename(url))

    if not os.path.exists(save_path):
        print(f"正在下载模型检查点文件：{url}")
        urllib.request.urlretrieve(url, save_path)
        print(f"模型检查点文件已保存到：{save_path}")
    else:
        print(f"模型检查点文件已存在：{save_path}")

    return save_path

@magic_factory(call_button="开始分割")
def sam_segmentation_widget(
    viewer: napari.viewer.Viewer,
    image_layer: Image,
    points_layer: Points,
    model_type: str = "vit_b",
    checkpoint_path: str = "",
):
    # 检测设备（GPU 或 CPU）
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"使用设备: {device}")

    # 如果没有提供检查点路径，下载默认的模型检查点文件
    if not checkpoint_path:
        cache_dir = os.path.expanduser("~/.cache/segment_anything")
        checkpoint_path = download_default_checkpoint(model_type, cache_dir)

    # 加载模型到指定设备
    sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
    sam.to(device)
    print(f"模型已加载到设备: {next(sam.parameters()).device}")

    predictor = SamPredictor(sam)

    # 获取图像数据
    image = image_layer.data

    # 如果是 Dask 数组，转换为 NumPy 数组
    if isinstance(image, da.core.Array):
        image = image.compute()

    # 检查图像维度
    if image.ndim != 3:
        print("图像应为 3D 数据，形状为 (Z, Y, X)")
        return

    # 获取提示点
    if points_layer is not None and len(points_layer.data) > 0:
        point_data = points_layer.data
        label_property = points_layer.properties.get('label', None)
        if label_property is None:
            point_labels = np.ones(len(points_layer.data), dtype=int)
        else:
            point_labels = np.array(label_property)
            if len(point_labels) != len(points_layer.data):
                print("点层的 'label' 属性长度与点的数量不一致。")
                return
    else:
        print("请在图像上添加提示点。")
        return

    z_indices = np.unique(point_data[:, 0].astype(int))
    print(f"包含提示点的切片索引: {z_indices}")

    masks = np.zeros_like(image, dtype=np.uint8)

    for z in z_indices:
        slice_image = image[z, :, :]

        if slice_image.ndim == 2:
            slice_image_rgb = np.stack([slice_image] * 3, axis=-1)
        elif slice_image.shape[2] == 1:
            slice_image_rgb = np.repeat(slice_image, 3, axis=2)
        else:
            slice_image_rgb = slice_image

        predictor.set_image(slice_image_rgb)

        mask_z = point_data[:, 0].astype(int) == z
        coords = point_data[mask_z][:, 1:]
        labels = point_labels[mask_z]

        if len(coords) == 0:
            continue

        coords = coords[:, ::-1]

        mask_slice, _, _ = predictor.predict(
            point_coords=coords,
            point_labels=labels,
            multimask_output=False,
        )
        
        print(f"Generated mask slice shape: {mask_slice.shape}, dtype: {mask_slice.dtype}")
        masks[z, :, :] = mask_slice[0]
        print(f"Updated mask at slice {z}. Non-zero values: {np.count_nonzero(masks[z, :, :])}")

    segmentation_layer_name = f"SAM 分割结果 ({image_layer.name})"
    if segmentation_layer_name in viewer.layers:
        segmentation_layer = viewer.layers[segmentation_layer_name]
        segmentation_layer.data = masks
        print(f"已更新标签层: {segmentation_layer_name}")
    else:
        viewer.add_labels(masks, name=segmentation_layer_name)
        print(f"已添加新的标签层: {segmentation_layer_name}")

def main():
    viewer = napari.Viewer()
    print("请在 napari 中加载一幅 3D 图像后，再运行分割。")

    widget = sam_segmentation_widget(
        viewer=viewer,
        image_layer=None,
        points_layer=None,
    )
    viewer.window.add_dock_widget(widget, area='right')

    def on_layer_change(event):
        active_layer = viewer.layers.selection.active
        if isinstance(active_layer, Image):
            widget.image_layer = active_layer
            points_layer = next((layer for layer in viewer.layers if isinstance(layer, Points) and layer.name == '提示点'), None)
            if not points_layer:
                points_layer = viewer.add_points(
                    name='提示点',
                    properties={'label': []},
                    face_color='label',
                    face_color_cycle=['red', 'blue'],
                    edge_color='white',
                    size=10,
                )
                print("已创建新的提示点层。")
            widget.points_layer = points_layer

    viewer.layers.events.inserted.connect(on_layer_change)
    viewer.layers.events.removed.connect(on_layer_change)
    viewer.layers.events.reordered.connect(on_layer_change)
    viewer.layers.events.moved.connect(on_layer_change)

    def on_click_add_point(layer, event):
        if event.type == 'mouse_press':
            label = 1 if event.button == 1 else 0 if event.button in {2, 3} else None
            if label is not None:
                position = event.position
                data_position = layer.world_to_data(position)
                layer.add([data_position], properties={'label': [label]})
                print(f"Added point: {data_position}, Label: {label}")
                print(f"All points in layer after addition: {layer.data}")
            else:
                print("Unsupported mouse button clicked.")

    def on_layer_change(event):
        active_layer = viewer.layers.selection.active
        if isinstance(active_layer, Image):
            widget.image_layer = active_layer
            points_layer = next((layer for layer in viewer.layers if isinstance(layer, Points) and layer.name == '提示点'), None)
            if not points_layer:
                points_layer = viewer.add_points(
                    name='提示点',
                    properties={'label': []},
                    face_color='red',  # Updated to use 'red' directly
                    edge_color='white',
                    size=10,
                )
                print("已创建新的提示点层。")
            widget.points_layer = points_layer


    viewer.layers.events.inserted.connect(connect_point_callbacks)
    viewer.layers.events.removed.connect(connect_point_callbacks)
    viewer.layers.events.reordered.connect(connect_point_callbacks)
    viewer.layers.events.moved.connect(connect_point_callbacks)

    napari.run()

if __name__ == '__main__':
    main()
