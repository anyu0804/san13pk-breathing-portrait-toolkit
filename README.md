# san13pk-breathing-portrait-toolkit

《三国志13威力加强版》（SAN13PK）呼吸立绘制作原型。Python + NumPy/Pillow，
输入 1024×1024 透明 PNG，输出胸/腰/头三层 32 位 BMP；提供选线建议和动画诊断。
本工具止步于 BMP，不自动写游戏包，也不附带第三方导入工具。

**成熟度：早期原型。矩形分层尚未用原生武将三层 alpha 校准；Photoshop 路径和
游戏内效果未实测。生成成功或测试通过都不代表游戏可用。**

## 当前分层模型

以下是工具的实验性模型，动画幅度和合成顺序也是预览假设，不是已经确认的游戏规则。

| 层 | 内容 | 预览运动 |
| --- | --- | --- |
| chest 胸层 | 胸线到腿线的局部躯干，上下向外羽化 | 绕胸线 ±1% 垂直缩放 |
| waist 腰层 | 腿线以下，上缘羽化 | 静止 |
| head 头层 | 胸线以上，下缘羽化 | 上下 ±2px 移动 |

三层共用 RGB，只修改 alpha。胸层不再保留整张原图，以免头层移动后露出旧头部。
Python 使用单向线性羽化，0px 表示硬切，负值拒绝。
局部重叠在半透明边缘可能增加不透明度；水平线也无法拟合肩—锁骨曲线、披风、武器。
因此移除了“alpha 取最大值等于原图即通过”的恒真检查，改为真实 source-over 合成诊断。

## 安装与快速体验

```bash
pip install -r requirements.txt
python examples/make_sample_portrait.py --out examples/sample_portrait.png
python scripts/pick_lines.py examples/sample_portrait.png --json examples/lines.json
python scripts/generate_breathing.py examples/sample_portrait.png --lines examples/lines.json
```

读取 `examples/lines.json` 的 `chest_line`，将下例 `300` 替换成实际建议值：

```bash
python scripts/verify_and_gif.py --prefix sample_portrait \
  --dir examples/sample_portrait_breathing --chest-line 300 \
  --source examples/sample_portrait.png
```

输出：

- `*_breathing_preview.gif`：灰底近似动画，使用 alpha over 混合。
- `*_frame_0.png` 到 `*_frame_3.png`：静态、中间和极值相位的透明 PNG，不受 GIF 调色板限制。
- `*_seams.png`：四个相位的黑白底对照，左黑右白，逐行对应相位 0、π/2、π、3π/2。
- `*_alpha_phases.json`：提供 `--source` 时，对全部相位统计原图 `alpha >= 250` 区域内
  合成后 `alpha < 250` 的像素数、最低 alpha、包围框与逐行计数（坐标均含端点）。
  默认只要有缺口就打印 `WARNING`，可用 `--warn-pixels` 调整像素数警告门槛，
  `--alpha-threshold` 调整 alpha 分界。这是原画布坐标比较，头部正常平移和
  外轮廓形变也可能被计入；警告不等于接缝已确认，更不是游戏验收。
- `*_static_diff.png`：提供 `--source` 时的静态 RGBA 绝对差异，控制台另报 alpha 差异。
  差异是诊断值，没有自动的游戏合格阈值；全透明像素的 RGB 差异也可能出现在图中。

请在全尺寸关键帧中观察胸线和腿线附近的缺口、旧轮廓、重复边缘与透明度变化。
GIF 只是近似运动，不能代替原生图对照或游戏内验收。

## 实际使用与线位

1. 保留原图，将立绘按比例排版到 1024×1024 透明画布，不要直接拉伸。
   社区旧资料常见人物有效图为 633×900；部分导入教程要求放在 1024 画布左上区域。
   这是待核对的布局线索，必须以目标版本导出的原生图和导入工具为准，不能一律居中。
2. `pick_lines.py` 只在可见主体高度 20%–35% 找最窄行作为颈到上胸候选，
   在 62%–80% 找腿线：限定宽度至少达到该候选区最大宽度的 80%，
   再取 41 行邻域内宽度梯度平均绝对值最小的位置（短主体缩小窗口）。
   这样优先选衣服内部平稳区域，避免裙摆下方的细腿；41 行对应默认 20px 羽化的邻域，
   80% 仍是启发式阈值，无法识别衣服。披风、武器、半身图或自定义羽化宽度仍需人工复核。
3. 看 `*_lines_preview.png`（红=胸线，蓝=腿线），通过 `--chest` 和 `--leg` 手动调整。
   胸线应结合肩颈运动，腿线结合衣摆遮挡；可调 `--feather-chest`（默认 7）、
   `--feather-leg`（默认 20）。这两个值是沿用社区经验的起始参数，不是本项目首次测定。
4. 用黑白底关键帧和 GIF 检查接缝，再使用自行获取的导入工具在副本上验证。
   导入及证据分级见 [import-workflow.md](docs/import-workflow.md)，
   格式线索见 [s13-package-format.md](docs/s13-package-format.md)。

## 原生图校准仍待完成

当前水平矩形分层是启发式制作模型，不能视为已复刻原生遮罩。
需要以来源明确、允许使用的原生三层样本核对覆盖范围、重叠区、肩颈曲线及画布位置，
并通过游戏确认各层运动角色、合成顺序和引擎变换参数。
这些校准和实机验收尚未完成。请勿向仓库上传官方原图、纹理像素或资源包。

## Photoshop 路径（不推荐，未实测）

**推荐使用 Python 路径。** PS 保存 BMP 时可能发生透明像素 RGB 被白底混合的情况，
羽化边缘因而可能出现白边；这是复审提出的推断，尚未在 Photoshop 中复现或排除。
当前脚本仍通过删除像素切层，不能承诺导出时 RGB 保真；只修复 Alpha 通道并不能证明没有白边。

如需研究 PS 路径，编辑 `photoshop/make_breathing.jsx` 顶部配置，用 File > Scripts > Browse 运行。
每层从原图独立 duplicate，选区按多边形坐标建立，透明度显式 store 到 Alpha 1，
BMP 使用 `BMPDepthType.THIRTYTWO`。输入必须为 1024×1024；尺寸错误会报错，不会拉伸。
输出三张 BMP 和一份原始 PSD。PS 原生高斯羽化与 Python 单向线性羽化**数值不同**，
不能互换参数或承诺逐像素一致。本轮仅做 API/控制流检查，未在 Photoshop 中运行。

## 测试

```bash
python -m compileall -q scripts tests examples
python -m unittest discover -s tests -v
```

回归用例包括示例旧腿线第 12/16 相位缺口复现、新腿线全部 16 相位裙摆带检查、
透明度缺口定位、零羽化、胸层范围、半透明 over 合成、移动头部残影、短主体选线、
BMP 回读及损坏文件。GitHub Actions 自动执行同一组用例；不覆盖 Photoshop 和游戏。

## 社区技术来源与致谢

三层 alpha、羽化和呼吸图导入是已有社区方法。本项目提供 Python 自动化、参数化选线
和诊断流程，不宣称发明这些原理，也不提供“完全独立原创”的鉴定。

- [乐观的宅神：PS 制作呼吸头像教程（2017，游民星空转载）](https://www.gamersky.com/handbook/201704/888527.shtml)
- [艾克氏遊戲人間：San13Pictool 早期介绍（2016）](https://xgodgame.blogspot.com/2016/02/13_2.html)
- [San13Pictool 导入教程（2017）](https://www.gamersky.com/handbook/201705/906839.shtml)

感谢 San13Pictool 作者 tkwlee 和历年来分享教程的社区作者。
本仓库只引用工具名称及教程链接，不打包或修改发布第三方工具，也不搬运教程图片。

## 第三方权利

本项目是非官方工具，与 KOEI TECMO GAMES CO., LTD. 无关联，亦未获得官方认可。
请只使用你有权使用的立绘，并遵守适用法律、游戏许可协议及第三方工具条款。
仓库不包含官方游戏资源、人物立绘或第三方美术素材；请勿提交解包图片、修改后的
官方资源包或受保护的二进制片段。

[MIT 许可证](LICENSE) 仅适用于项目权利人有权授权的原创代码和文档，不授予第三方
游戏、美术作品或商标的使用权。格式研究不等于获得逆向、修改或传播的普遍授权；
本项目不承诺 EULA 或版权风险为零。

## English summary

Experimental SAN13PK portrait-layer generator using Python, NumPy and Pillow.
Torso-only masks, alpha-over animation diagnostics and regression tests are provided.
Native alpha calibration and motion roles remain unverified.
The Photoshop path is not recommended due to an untested RGB/white-fringe concern. In-game acceptance is not run.
No game assets or third-party tools are distributed. MIT covers only licensable project content.
