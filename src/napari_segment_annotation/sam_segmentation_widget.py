# sam_napari_plugin.py

import os
import urllib.request
import numpy as np
import dask.array as da
import napari
from magicgui import magic_factory
from napari.layers import Image, Labels, Points
from segment_anything import sam_model_registry, SamPredictor

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

@magic_factory(call_button="Segment")
def sam_segmentation_widget(
    viewer: napari.viewer.Viewer,
    image_layer: Image,
    points_layer: Points,
    model_type: str = "vit_b",
    checkpoint_path: str = "",
):
    # 如果没有提供检查点路径，下载默认的模型检查点文件
    if not checkpoint_path:
        cache_dir = os.path.expanduser("~/.cache/segment_anything")
        checkpoint_path = download_default_checkpoint(model_type, cache_dir)

    # 加载模型
    sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
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

    # 初始化掩码列表
    masks = []

    # 遍历每个切片
    for i in range(image.shape[0]):  # 假设 Z 轴在第 0 维
        slice_image = image[i, :, :]

        # 将灰度图像转换为 RGB
        if slice_image.ndim == 2:
            slice_image_rgb = np.stack([slice_image] * 3, axis=-1)
        elif slice_image.shape[2] == 1:
            slice_image_rgb = np.repeat(slice_image, 3, axis=2)
        else:
            slice_image_rgb = slice_image  # 如果已经是 RGB，则不处理

        # 设置图像
        predictor.set_image(slice_image_rgb)

        # 筛选在当前切片的点
        mask_z = point_data[:, 0] == i
        coords = point_data[mask_z][:, 1:]  # 获取 Y, X 坐标
        labels = point_labels[mask_z]

        if len(coords) == 0:
            # 如果当前切片没有点，则添加全零掩码
            masks.append(np.zeros(slice_image.shape[:2], dtype=np.uint8))
            continue

        # 将坐标从 (Y, X) 转换为 (X, Y)，因为 SAM 需要的是 (X, Y)
        coords = coords[:, ::-1]

        # 进行预测
        mask_slice, _, _ = predictor.predict(
            point_coords=coords,
            point_labels=labels,
            multimask_output=False,
        )

        masks.append(mask_slice[0])

    # 重建 3D 掩码
    mask_volume = np.stack(masks, axis=0)

    # 添加分割结果到 napari
    viewer.add_labels(mask_volume, name=f"SAM Segmentation ({image_layer.name})")

def main():
    # 创建 napari Viewer
    viewer = napari.Viewer()

    # 加载您的 3D 图像
    # 请将 'your_image_data' 替换为您的实际图像数据
    # 例如：
    # image_data = np.load('your_image.npy')  # 或者使用其他方式加载图像
    # image_layer = viewer.add_image(image_data, name='Your Image')

    # 假设您已经有一个名为 'Your Image' 的图像层
    image_layer = viewer.layers['Your Image']

    # 创建自定义点层
    points_layer = viewer.add_points(
        name='Interactive Points',
        properties={'label': []},  # 初始化空的 'label' 属性
        face_color='label',
        face_color_cycle=['red', 'blue'],  # 1: 红色（前景），0: 蓝色（背景）
        edge_color='white',
        size=10,
    )

    # 定义鼠标事件回调函数
    def on_click_add_point(layer, event):
        if event.type == 'mouse_press':
            if event.button == 1:  # 左键
                label = 1  # 前景
            elif event.button == 2 or event.button == 3:  # 右键
                label = 0  # 背景
            else:
                return

            # 获取鼠标点击的位置
            position = event.position  # 世界坐标
            # 将世界坐标转换为数据坐标
            data_position = layer.world_to_data(position)

            # 添加点和属性
            layer.add([data_position], properties={'label': [label]})

    # 连接鼠标事件回调
    points_layer.mouse_press_callbacks.append(on_click_add_point)

    # 将插件添加到 napari 界面
    widget = sam_segmentation_widget(
        viewer=viewer,
        image_layer=image_layer,
        points_layer=points_layer,
    )
    viewer.window.add_dock_widget(widget, area='right')

    napari.run()

if __name__ == '__main__':
    main()
