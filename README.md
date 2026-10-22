# san13pk-breathing-portrait-toolkit

《三国志13威力加强版》（SAN13PK）**呼吸立绘制作工具**：把一张 1024×1024 的
透明全身立绘，切成游戏呼吸动画所需的胸/腰/头三层羽化 BMP，并附带动画预览、
自动选线和资源包格式文档。

不依赖 Photoshop（纯 Python + numpy/Pillow）；也提供 Photoshop 脚本作为备选路径。

## 原理

游戏里的"呼吸立绘"不是视频，而是三张同尺寸图层叠出来的动画：

| 层 | 文件 | 内容 | 动画 |
| --- | --- | --- | --- |
| chest 胸层 | `<prefix>_chest.bmp` | **完整原图** | 绕胸线做 ±1% 垂直缩放（呼吸起伏） |
| waist 腰层 | `<prefix>_waist.bmp` | 腿线以下（上缘羽化） | 静止，垫底遮住胸层缩放产生的腿部位移 |
| head 头层 | `<prefix>_head.bmp` | 胸线以上（下缘羽化） | 上下 ±2px 浮动（点头） |

命名沿用了光荣 modding 社区"胸图/腰图/头图"的习惯。三张图都是 1024×1024、
32 位 BGRA、无压缩 BMP；同一像素在各层的颜色数据一致，只靠 alpha 和羽化分配
层次，所以叠加回去就是原图（生成时会自动校验这一点）。

## 安装

```bash
pip install -r requirements.txt   # numpy + pillow
```

## 快速体验（合成示例，零素材）

```bash
cd examples
python make_sample_portrait.py                       # 生成合成立绘 sample_portrait.png
python ../scripts/pick_lines.py sample_portrait.png --json lines.json   # 自动建议胸线/腿线
python ../scripts/generate_breathing.py sample_portrait.png --lines lines.json
python ../scripts/verify_and_gif.py --prefix sample_portrait \
    --dir sample_portrait_breathing --chest-line <lines.json 里的 chest_line>
```

`verify_and_gif.py` 会校验三张 BMP 的文件头并输出 `*_breathing_preview.gif`
（灰底模拟呼吸动画），肉眼检查接缝即可。

## 实际使用

1. **准备立绘**：1024×1024、带透明通道的全身 PNG（半身/无边框；画布和透明
   边缘要求见游戏原生呼吸图，可用 `make_preview.py` 在灰底/白底/黑底上检查
   白边黑边）。
2. **定线位**：`pick_lines.py` 给建议值，但务必看生成出的
   `<prefix>_lines_preview.png`（红线=胸线，蓝线=腿线）人工微调：
   - 胸线：落在颈部到胸口之间，头层浮动时肩部不穿帮；
   - 腿线：落在裙摆/胯部有遮挡的位置，腰层上缘不露断口。
3. **生成分层**：`generate_breathing.py`，可调 `--feather-chest`（默认 7px）、
   `--feather-leg`（默认 20px）羽化宽度。
4. **验收**：`verify_and_gif.py` 出 GIF 预览；三图合成 alpha 最大差异应为 0
   （羽化区内允许小量）。
5. **导入游戏**：本工具止步于 BMP。导入与槽位定位见
   [docs/import-workflow.md](docs/import-workflow.md)（暂存包、回读、验收的
   安全流程）和 [docs/s13-package-format.md](docs/s13-package-format.md)
   （DATA0/DATA1 资源包结构、bundle 用途、纹理格式线索）。导入工具
   （官方头像工具、San13Pictool 等）需自行获取，本仓库不提供。

## Photoshop 备选路径

`photoshop/make_breathing.jsx`：改好顶部 CONFIG 块（源图路径、线位），
File > Scripts > Browse... 运行，输出与 Python 版相同的三张 BMP + 一份
可继续手动调整的 PSD 底稿。羽化用 PS 原生选区羽化实现，与 Python 版
数值一致。

## 注意事项

- 各游戏版本（PK 版本号/语言/补丁）的资源包结构可能不同，导入前务必按
  docs 里的流程现场确认，不要照搬任何固定偏移。
- 本仓库只含制作工具和格式文档，**不含任何游戏资产、官方素材或第三方
  导入工具**；导入修改游戏文件的风险自担，记得先备份。
- 呼吸图动画参数（缩放幅度、浮动像素）由游戏引擎决定，本工具的 GIF 预览
  只是近似模拟。

## English summary

Toolkit for making "breathing portrait" layers for Romance of the Three
Kingdoms XIII Fame & Strategy (SAN13PK): splits a 1024×1024 RGBA full-body
portrait into three feathered BMP layers (chest / waist / head) that the
game composites into its breathing animation. Includes automatic line
picking, layered-alpha verification, an animated GIF preview approximating
the in-game effect, a Photoshop alternative script, and reverse-engineered
notes on the S13 resource package format. Python + numpy + Pillow only.

## License

[MIT](LICENSE)
