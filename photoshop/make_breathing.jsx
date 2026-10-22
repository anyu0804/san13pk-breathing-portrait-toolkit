#target photoshop

// 三国志13PK 呼吸图自动制作脚本（Photoshop 备选路径）
// 输入: 1024x1024 带透明通道的全身立绘 PNG
// 输出: 三张 32位带 Alpha 的 BMP（chest=全身 / waist=腿以下 / head=头到胸口）+ 底图 PSD
//
// 用法：把下方 CONFIG 块改成自己的路径和线位（可用 pick_lines.py 建议值），
// 在 Photoshop 里 File > Scripts > Browse... 运行本文件。
// 默认 Python 脚本（scripts/generate_breathing.py）不需要 Photoshop，殊途同归。

// ===== CONFIG（按需修改） =====
var SRC = "C:/path/to/portrait.png";      // 源图 PNG
var OUT_BASE = "C:/path/to/out/portrait"; // 输出前缀（不带扩展名）
var CHEST_LINE = 465;                     // 胸线 y（0 在顶部）
var LEG_LINE = 658;                       // 腿线 y
var FEATHER_WAIST = 20;                   // 腰层上缘羽化 px
var FEATHER_HEAD = 7;                     // 头层下缘羽化 px
// =============================

var LOG_FILE = OUT_BASE + "_log.txt";

function log(msg) {
    var f = new File(LOG_FILE);
    f.open("a");
    f.writeln(msg);
    f.close();
}

function selectLayerTransparency() {
    var idSlct = charIDToTypeID("slct");
    var d = new ActionDescriptor();
    d.putEnumerated(charIDToTypeID("Chnl"), charIDToTypeID("Chnl"), charIDToTypeID("Trsp"));
    executeAction(idSlct, d, DialogModes.NO);
}

function rebuildAlpha1() {
    // 先把已有 Alpha 1 删掉，再根据当前图层透明区域重建
    try {
        var ch = doc.channels["Alpha 1"];
        if (ch) ch.remove();
    } catch (e) {}
    selectLayerTransparency();
    var newCh = doc.channels.add();
    try { newCh.name = "Alpha 1"; } catch (e) {}
    doc.selection.deselect();
}

function saveBmp(path) {
    var f = new File(path);
    if (f.exists) f.remove();
    var opts = new BMPSaveOptions();
    opts.alphaChannels = true;
    opts.OS = OperatingSystem.WINDOWS;
    try { opts.depth = BitsPerChannelType.THIRTYTWO; } catch (e) {
        try { opts.depth = 32; } catch (e2) {}
    }
    doc.saveAs(f, opts, true, Extension.LOWERCASE);
    log("saved " + path);
}

function cutRect(x1, y1, x2, y2, featherPx) {
    doc.selection.deselect();
    doc.selection.select([x1, y1, x2, y2], SelectionType.REPLACE, 0, false);
    if (featherPx > 0) doc.selection.feather(featherPx);
    doc.selection.clear();
    doc.selection.deselect();
}

app.displayDialogs = DialogModes.NO;
try {
    var f0 = new File(LOG_FILE);
    if (f0.exists) f0.remove();
} catch (e) {}

var src = new File(SRC);
var doc = open(src);
if (!doc) {
    log("ERROR 无法打开源图: " + SRC);
    throw new Error("无法打开源图");
}

// 确保 1024x1024（源图应为 1024x1024，若尺寸不同则缩放并居中）
var W = doc.width.value, H = doc.height.value;
if (W != 1024 || H != 1024) {
    doc.resizeImage(1024, 1024, null, ResampleMethod.BICUBIC);
}

rebuildAlpha1();
saveBmp(OUT_BASE + "_chest.bmp");

// 底图 PSD（方便以后手动调整线位）
var psdPath = OUT_BASE + "_base.psd";
var psdFile = new File(psdPath);
if (psdFile.exists) psdFile.remove();
doc.saveAs(psdFile, new PhotoshopSaveOptions(), true, Extension.LOWERCASE);

// 腰图: 保留腿线以下，上方羽化
cutRect(0, 0, 1024, LEG_LINE, FEATHER_WAIST);
rebuildAlpha1();
saveBmp(OUT_BASE + "_waist.bmp");

// 头图: 保留胸线以上，下方羽化
cutRect(0, CHEST_LINE, 1024, 1024, FEATHER_HEAD);
rebuildAlpha1();
saveBmp(OUT_BASE + "_head.bmp");

log("DONE");
