# 本地语音推理

KGTS 默认使用项目内的 `Genie-TTS` 推理特化运行本地 TTS。

这个能力面向本地或高资源 VM。Azure App Service F1 和 Azure for Students 1 GB 免费 VM 默认都应禁用 TTS，避免模型体积、内存和冷启动时间拖垮主站。

- 推理代码：`third_party/Genie-TTS`
- 公共资源：`models/tts/GenieData`
- `shu` ONNX 模型：`models/tts/shu`
- 参考音频：`models/tts/shu/reference/shu.wav`
- 生成音频缓存：`.runtime/tts/audio`

`gpt_sovits_local` 仍作为兼容 provider 保留，但不是默认运行路径。默认配置不再依赖 `D:\download\TTS\GPT-SoVITS-20240821v2`；兼容运行时默认只会查找项目内 `.runtime/tts/gpt-sovits`。

## 默认配置

本地根目录 `.env` 中应保留：

```text
KGTS_TTS_ENABLED=1
KGTS_TTS_PROVIDER=genie
KGTS_TTS_GENIE_DATA_DIR=models/tts/GenieData
KGTS_TTS_MODEL_DIR=models/tts/shu
KGTS_TTS_CHARACTER_NAME=shu
KGTS_TTS_LANGUAGE=zh
KGTS_TTS_REFERENCE_AUDIO=models/tts/shu/reference/shu.wav
KGTS_TTS_REFERENCE_LANGUAGE=zh
KGTS_TTS_REFERENCE_TEXT=我是谁？答案只在于我所见所遇的一切。
KGTS_PROJECT_LOCAL_ONLY=1
KGTS_ALLOW_EXTERNAL_PATHS=0
```

启动 KGTS 后检查：

```bash
curl http://127.0.0.1:8000/api/tts/status
```

返回的 `provider` 应为 `genie`，`available` 应为 `true`。

如果配置了项目外路径，状态接口会返回 `outside_project_paths` 和明确的 `detail`。仅调试迁移旧资产时才建议临时设置 `KGTS_ALLOW_EXTERNAL_PATHS=1`。

## 模型来源

`models/tts/shu` 是由本地 GPT-SoVITS `shu` 权重转换得到的 Genie ONNX 模型：

- `GPT_weights_v2/shu-e15.ckpt`
- `SoVITS_weights_v2/shu_e8_s368.pth`

转换后的运行文件约 237MB。`GenieData` 公共资源约 344MB。两者合计约 581MB，不包含生成音频缓存。

## 长文本播放策略

当前可用策略是“分段合成、边播边预取”：

- 前端对长于约 420 字的讲稿先调用 `POST /api/tts/segments`。
- 后端按段落、句号、分号、逗号逐级切分，默认单段约 260 字。
- 前端先合成并播放第 1 段，当前段开始播放后后台预取后续 2 段。
- 状态栏显示当前段、就绪段数、后台生成数、缓存命中数和 provider。
- 终端会打印 `[tts] synthesize:start` / `[tts] synthesize:done`，包含 provider、字符数、缓存状态、文件名和耗时。

这不是字节级真流式；Genie-TTS 仍要先生成 wav 文件，再由浏览器播放。当前实现已经把“播放当前段”和“预取后续段”并行起来。

## 线上部署建议

轻量线上部署建议使用：

```text
KGTS_TTS_ENABLED=0
KGTS_TTS_PROVIDER=disabled
```

如果需要线上语音，优先把 TTS 独立部署到更高内存 VM 或专门推理服务，再让主站通过 server provider 调用，不要把 GenieData、ONNX 模型、缓存音频和主 Web 进程放在同一个 1 GB 免费 VM 里。
