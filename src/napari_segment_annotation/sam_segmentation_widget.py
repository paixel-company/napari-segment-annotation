# sam_napari_plugin.py

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
    # 根据 SamPredictor 的实现，确保其使用相同的设备
    # 假设 SamPredictor 内部会自动处理设备迁移

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
            # 如果没有 'label' 属性，默认将所有点的标签设为 1（前景）
            point_labels = np.ones(len(points_layer.data), dtype=int)
        else:
            point_labels = np.array(label_property)
            # 检查 'label' 属性的长度是否与点的数量一致
            if len(point_labels) != len(points_layer.data):
                print("点层的 'label' 属性长度与点的数量不一致。请确保每个点都有对应的 'label' 值。")
                return
    else:
        print("请在图像上添加提示点。")
        return

    # 获取包含提示点的切片索引
    z_indices = np.unique(point_data[:, 0].astype(int))
    print(f"包含提示点的切片索引: {z_indices}")

    # 初始化掩码列表
    masks = np.zeros_like(image, dtype=np.uint8)  # 初始化整个3D掩码为0

    # 遍历包含提示点的切片
    for z in z_indices:
        slice_image = image[z, :, :]

        # 将灰度图像转换为 RGB
        if slice_image.ndim == 2:
            slice_image_rgb = np.stack([slice_image] * 3, axis=-1)
        elif slice_image.shape[2] == 1:
            slice_image_rgb = np.repeat(slice_image, 3, axis=2)
        else:
            slice_image_rgb = slice_image  # 如果已经是 RGB，则不处理

        # 设置图像到预测器
        predictor.set_image(slice_image_rgb)

        # 筛选在当前切片的点
        mask_z = point_data[:, 0].astype(int) == z
        coords = point_data[mask_z][:, 1:]  # 获取 Y, X 坐标
        labels = point_labels[mask_z]

        if len(coords) == 0:
            # 如果当前切片没有点，则跳过
            continue

        # 将坐标从 (Y, X) 转换为 (X, Y)，因为 SAM 需要的是 (X, Y)
        coords = coords[:, ::-1]

        # 进行预测
        mask_slice, _, _ = predictor.predict(
            point_coords=coords,
            point_labels=labels,
            multimask_output=False,
        )

        # 将预测的掩码应用到整个3D掩码中
        masks[z, :, :] = mask_slice[0]

    # 检查是否已存在分割标签层
    segmentation_layer_name = f"SAM 分割结果 ({image_layer.name})"
    if segmentation_layer_name in viewer.layers:
        # 更新现有的标签层数据
        segmentation_layer = viewer.layers[segmentation_layer_name]
        segmentation_layer.data = masks
        print(f"已更新标签层: {segmentation_layer_name}")
    else:
        # 添加新的标签层
        viewer.add_labels(masks, name=segmentation_layer_name)
        print(f"已添加新的标签层: {segmentation_layer_name}")

def main():
    # 创建 napari Viewer
    viewer = napari.Viewer()

    # 提示用户加载图像
    print("请在 napari 中加载一幅 3D 图像后，再运行分割。")

    # 添加自定义插件按钮到 Napari
    widget = sam_segmentation_widget(
        viewer=viewer,
        image_layer=None,  # 初始时不指定图像层，用户需在界面中选择
        points_layer=None,  # 初始时不指定点层
    )
    viewer.window.add_dock_widget(widget, area='right')

    # 定义当图像层被选择时，自动设置 image_layer 和 points_layer
    def on_layer_change(event):
        # 查找当前活动的图像层
        active_layer = viewer.layers.selection.active
        if isinstance(active_layer, Image):
            widget.image_layer = active_layer
            # 如果没有点层，创建一个新的点层
            points_layer = next((layer for layer in viewer.layers if isinstance(layer, Points) and layer.name == '提示点'), None)
            if not points_layer:
                points_layer = viewer.add_points(
                    name='提示点',
                    properties={'label': []},  # 初始化空的 'label' 属性
                    face_color='label',
                    face_color_cycle=['red', 'blue'],  # 1: 红色（前景），0: 蓝色（背景）
                    edge_color='white',
                    size=10,
                )
                print("已创建新的提示点层。")
            widget.points_layer = points_layer

    # 连接图层变化事件
    viewer.layers.events.inserted.connect(on_layer_change)
    viewer.layers.events.removed.connect(on_layer_change)
    viewer.layers.events.reordered.connect(on_layer_change)
    viewer.layers.events.moved.connect(on_layer_change)

    # 定义鼠标事件回调函数
    def on_click_add_point(layer, event):
        if event.type == 'mouse_press':
            if event.button == 1:  # Left-click
                label = 1  # Foreground
            elif event.button == 2 or event.button == 3:  # Right-click
                label = 0  # Background
            else:
                return
            print("lable: ", label)

            # Get mouse click position
            position = event.position  # World coordinates
            # Convert world coordinates to data coordinates
            data_position = layer.world_to_data(position)

            # Add point and property
            layer.add([data_position], properties={'label': [label]})
            print(f"Added point: {data_position}, Label: {label}")


    # 连接鼠标事件回调
    # 这里假设 points_layer 已经被正确设置
    # 如果 points_layer 可能为 None，需要在后续事件中动态连接
    def connect_point_callbacks():
        points_layers = [layer for layer in viewer.layers if isinstance(layer, Points)]
        for layer in points_layers:
            if on_click_add_point not in layer.mouse_press_callbacks:
                layer.mouse_press_callbacks.append(on_click_add_point)
                print(f"已连接鼠标事件回调到点层: {layer.name}")

    # 连接点层变化事件
    viewer.layers.events.inserted.connect(connect_point_callbacks)
    viewer.layers.events.removed.connect(connect_point_callbacks)
    viewer.layers.events.reordered.connect(connect_point_callbacks)
    viewer.layers.events.moved.connect(connect_point_callbacks)

    napari.run()

if __name__ == '__main__':
    main()
