# 本地语音推理

KGTS 默认使用项目内的 `Genie-TTS` 推理特化运行本地 TTS。

这个能力面向本地或高资源 VM。Azure App Service F1 和 Azure for Students 1 GB 免费 VM 的主站不应直接加载本地 TTS 权重；线上默认保持 TTS 接口启用，并通过 `genie_server` 代理调用独立推理服务，避免模型体积、内存和冷启动时间拖垮主站。

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

## 音频有效性校验

KGTS 会在写入或转发 TTS 音频后校验 WAV 文件是否真实可播放：

- 本地 `genie` provider 会等待输出文件大小短暂稳定，再检查 WAV 头、声道、采样宽度、采样率和帧数。
- `genie_server` provider 会拒绝空响应、HTML/JSON 错误页或其它非 WAV 内容，并删除无效缓存文件。
- 独立 `scripts/genie_tts_proxy_server.py` 返回文件前也会做同样校验，避免上游生成半截文件时主站缓存坏音频。

如果接口返回 `not a valid WAV file`、`empty or incomplete` 或 `no playable audio frames`，优先检查 TTS 代理日志、模型是否 OOM、参考音频路径是否存在，以及代理是否把异常页当成音频返回。修复后重新合成即可生成新的缓存文件。

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

## 公式朗读

TTS 合成前会先在后端把 LaTeX 公式转换成可朗读文本。默认配置为：

```text
KGTS_TTS_FORMULA_ENGINE=sre
KGTS_TTS_FORMULA_TIMEOUT_SECONDS=3
```

`sre` 模式通过 `scripts/latex_speech_cli.cjs` 调用前端依赖里的 MathJax 和 Speech Rule Engine，把 `$...$`、`$$...$$`、`\(...\)`、`\[...]` 以及裸 `\frac{...}{...}` 转换成公式朗读文本。分式、根号、求和、积分、矩阵等结构化 LaTeX 会优先走这条链路；简单裸表达式仍保留 Python 内置规则，避免把 `p_0 > 1/(2Ns)` 这类短式子读得更差。

如果 VM 或本地环境没有安装 Node 依赖，或者公式转换超时/失败，系统会自动回退到 Python 内置转换，不会让 `/api/tts/synthesize` 因公式朗读引擎缺失而整体失败。更新部署时执行 `cd frontend && npm ci` 即可安装所需 Node 包。

## 线上部署建议

轻量线上部署建议使用：

```text
KGTS_TTS_ENABLED=1
KGTS_TTS_PROVIDER=genie_server
KGTS_TTS_SERVER_URL=http://127.0.0.1:9880
```

把 TTS 独立部署到更高内存 VM、专门推理服务，或单独的本机代理进程，再让主站通过 server provider 调用；不要把 GenieData、ONNX 模型、缓存音频和主 Web 进程放在同一个 1 GB 免费 VM 进程里。1 GB 免费 VM 上如需同时保留本地图结构向量检索能力，按错峰任务处理：TTS 只用于朗读课件，向量检索只用于备课/问答。

## 受限 VM 实验：独立 Genie 代理

Azure for Students 1 GB VM 可以尝试把主站和 TTS 分离成两个本机服务。主站配置成代理模式：

```text
KGTS_TTS_ENABLED=1
KGTS_TTS_PROVIDER=genie_server
KGTS_TTS_SERVER_URL=http://127.0.0.1:9880
```

另起一个进程运行本地 Genie：

```bash
KGTS_TTS_GENIE_LOW_MEMORY=1 \
KGTS_TTS_ONNX_CACHE_DIR=.runtime/tts/onnx-fp32-cache \
KGTS_TTS_PROXY_UNLOAD_AFTER_SYNTH=1 \
KGTS_TTS_PROXY_EXIT_AFTER_SYNTH=1 \
python scripts/genie_tts_proxy_server.py
```

中英混合朗读必须让 Genie 的 `hybrid-zh-en` 路径可用，而不是把英文术语按中文拼读。确认 TTS 虚拟环境安装了 `nltk`，并且 `models/tts/GenieData/G2P/EnglishG2P/` 下至少包含：

```text
checkpoint20.npz
engdict_cache.pickle
namedict_cache.pickle
taggers/averaged_perceptron_tagger_eng/
wordsegment/
cmudict.rep
cmudict-fast.rep
engdict-hot.rep
```

如果缺少前三个文件，可以从 Genie 官方模型仓库补齐：

```bash
. .venv/bin/activate
python - <<'PY'
from huggingface_hub import hf_hub_download
from pathlib import Path

target = Path("models/tts/GenieData/G2P/EnglishG2P")
target.mkdir(parents=True, exist_ok=True)
for name in ["checkpoint20.npz", "engdict_cache.pickle", "namedict_cache.pickle"]:
    path = hf_hub_download(
        repo_id="High-Logic/Genie",
        repo_type="model",
        filename=f"GenieData/G2P/EnglishG2P/{name}",
        local_dir=".runtime/tts/downloads/genie-english-g2p",
    )
    (target / name).write_bytes(Path(path).read_bytes())
PY
sudo systemctl restart kgts-tts
```

验证时日志应出现 `lang=hybrid-zh-en`，而不是 `lang=zh`。

`core/genie_low_memory.py` 会在代理进程里给 Genie-TTS 打运行时补丁：把 FP16 外部权重分块转换成可复用的 FP32 外部权重缓存，让 ONNX Runtime 从磁盘文件加载，避免一次性把完整 FP16、FP32 和序列化 ONNX 都放进 Python 内存。这个补丁降低的是加载峰值，不会改变模型本身需要的常驻内存。

实际 1 GB VM 上仍要把它视为实验配置：`shu` 模型的 T2S 两个 decoder 各引用约 293 MB FP32 权重，VITS 约 154 MB，CN-HuBERT 约 360 MB；即使磁盘模型只有约 581 MB，ONNX Runtime 加载后也可能超过免费 VM 可用内存。代理进程的价值是保护主站，TTS OOM 时只重启代理，不拖垮页面和其它 API。

在 1 GB VM 上建议开启 `KGTS_TTS_PROXY_UNLOAD_AFTER_SYNTH=1` 和 `KGTS_TTS_PROXY_EXIT_AFTER_SYNTH=1`。前者会在每次合成后释放 Genie 角色模型、HuBERT 和引用音频缓存；后者会让代理在响应发出后退出并由 systemd 重启，以绕过 ONNX Runtime 内存不完全归还的问题。
