# 素材放置说明

把图片按下面的**文件名和路径**放进来，保持命名一致，我再接进代码。`public/` 下的文件在网页里用 `/assets/...` 引用。

两套主题各一份：`lunar/`（写实月面）、`pixel/`（复古像素）。同名不同风格，一套写实/高清，一套像素。

## 目录结构

```
public/assets/
  lunar/
    background.jpg          月表背景图（写实）
    rover.png              小车贴图（俯视，车头朝上）
    icons/
      ship.png             飞船基地
      fuel.png             资源 / 燃料
      relic.png            遗迹
      dust.png             月尘
      meteor.png           陨石
      jam.png              干扰
  pixel/
    background.png          太空/月面背景（像素）
    rover.png              小车（像素，车头朝上）
    icons/
      ship.png
      fuel.png
      relic.png
      dust.png
      meteor.png
      jam.png
```

## 规格建议

| 文件 | 格式 | 尺寸 | 说明 |
| --- | --- | --- | --- |
| `background.*` | jpg 或 png | 建议 ≥ 1600×1600（地图是正方形） | 深色、纹理清晰；写实用 jpg，像素用 png |
| `rover.png` | png 透明 | 约 128×128 | **车头朝上（北）**，我按角度旋转；单色即可，颜色由四周光晕区分阵营 |
| `icons/*.png` | png 透明 | 约 128×128 | 居中、边距留一点；写实矢量风或像素风与各自主题一致 |

## 说明

- 只填一套也行，另一套没图时自动回退到现在的 CSS/SVG 画法，不会报错。
- 图标一套 6 个：ship / fuel / relic / dust / meteor / jam，对应地图六类区域。
- 小车只要一张（朝上），四台车靠颜色光晕和编号区分，不用做四份。
- 放好后把"哪套齐了"告诉我，我把 emoji 图标、纯 CSS 背景换成这些贴图。
