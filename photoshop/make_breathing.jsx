#target photoshop

// 实验性矩形分层；PS 高斯羽化与 Python 单向线性羽化不同。
// 必须输入 1024x1024 透明 PNG；不会拉伸、移动或覆盖原文件。
var SRC = "C:/path/to/portrait.png";
var OUT_BASE = "C:/path/to/out/portrait";
var CHEST_LINE = 465;
var LEG_LINE = 658;
var FEATHER_WAIST = 20;
var FEATHER_HEAD = 7;

function rebuildAlpha1(doc) {
    // PNG 副本只保留 RGB 和当前透明度生成的 Alpha，避免保存陈旧通道。
    for (var i = doc.channels.length - 1; i >= 0; i--) {
        if (doc.channels[i].kind != ChannelType.COMPONENT) doc.channels[i].remove();
    }
    var d = new ActionDescriptor();
    var selection = new ActionReference();
    selection.putProperty(charIDToTypeID("Chnl"), charIDToTypeID("fsel"));
    d.putReference(charIDToTypeID("null"), selection);
    var transparency = new ActionReference();
    transparency.putEnumerated(charIDToTypeID("Chnl"), charIDToTypeID("Chnl"), charIDToTypeID("Trsp"));
    d.putReference(charIDToTypeID("T   "), transparency);
    executeAction(charIDToTypeID("setd"), d, DialogModes.NO);
    var alpha = doc.channels.add();
    alpha.name = "Alpha 1";
    doc.selection.store(alpha, SelectionType.REPLACE);
    doc.selection.deselect();
    doc.activeChannels = [doc.channels[0], doc.channels[1], doc.channels[2]];
}

function cutRect(doc, x1, y1, x2, y2, featherPx) {
    doc.selection.select([[x1,y1], [x2,y1], [x2,y2], [x1,y2]], SelectionType.REPLACE, 0, false);
    if (featherPx > 0) doc.selection.feather(featherPx);
    doc.selection.clear();
    doc.selection.deselect();
}

function exportLayer(source, tag) {
    var doc = source.duplicate(tag);
    try {
        if (tag == "chest") {
            cutRect(doc, 0, 0, 1024, CHEST_LINE, FEATHER_HEAD);
            cutRect(doc, 0, LEG_LINE, 1024, 1024, FEATHER_WAIST);
        } else if (tag == "waist") {
            cutRect(doc, 0, 0, 1024, LEG_LINE, FEATHER_WAIST);
        } else {
            cutRect(doc, 0, CHEST_LINE, 1024, 1024, FEATHER_HEAD);
        }
        rebuildAlpha1(doc);
        var opts = new BMPSaveOptions();
        opts.alphaChannels = true;
        opts.OS = OperatingSystem.WINDOWS;
        opts.depth = BMPDepthType.THIRTYTWO;
        opts.rleCompression = false;
        doc.saveAs(new File(OUT_BASE + "_" + tag + ".bmp"), opts, true, Extension.LOWERCASE);
    } finally {
        doc.close(SaveOptions.DONOTSAVECHANGES);
    }
}

function main() {
    if (!(0 < CHEST_LINE && CHEST_LINE < LEG_LINE && LEG_LINE < 1024)
        || FEATHER_WAIST < 0 || FEATHER_HEAD < 0) {
        throw new Error("需要 0 < 胸线 < 腿线 < 1024；羽化宽度 >= 0");
    }
    var dialogs = app.displayDialogs;
    app.displayDialogs = DialogModes.NO;
    try {
        var source = app.open(new File(SRC));
        try {
            if (source.width.as("px") != 1024 || source.height.as("px") != 1024) {
                throw new Error("输入必须是 1024x1024；请先按比例缩放并排版到透明画布");
            }
            source.saveAs(new File(OUT_BASE + "_base.psd"), new PhotoshopSaveOptions(), true, Extension.LOWERCASE);
            exportLayer(source, "chest");
            exportLayer(source, "waist");
            exportLayer(source, "head");
        } finally {
            source.close(SaveOptions.DONOTSAVECHANGES);
        }
    } finally {
        app.displayDialogs = dialogs;
    }
}
main();
