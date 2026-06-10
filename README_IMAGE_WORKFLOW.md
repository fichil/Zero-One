# Zero-One Image Workflow

这个流程会读取 `episodes/ep001_moon_pink.json`，按每个 shot 的 `image_prompt` 批量生成第一集分镜图。

## 配置

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

设置 OpenAI API Key。不要把 key 写进代码，也不要提交 `.env` 文件。

临时设置当前 PowerShell 会话：

```powershell
$env:OPENAI_API_KEY="sk-your-key"
```

也可以在本地创建 `.env` 文件：

```text
OPENAI_API_KEY=sk-your-key
```

脚本会在安装了 `python-dotenv` 时自动读取 `.env`。

## 运行

默认读取 `episodes/ep001_moon_pink.json`，使用 `gpt-image-2` 和 `1024x1536`：

```powershell
python scripts/generate_images_openai.py
```

先做小成本测试，只实际生成 1 张图片：

```powershell
python scripts/generate_images_openai.py --limit 1
```

`--limit` 统计的是实际调用 OpenAI Images API 生成的图片数。已存在图片且未使用 `--force` 时会跳过，不计入 `--limit`。

如果图片已存在，默认跳过。需要覆盖重生成时传入：

```powershell
python scripts/generate_images_openai.py --force
```

也可以显式指定模型和尺寸：

```powershell
python scripts/generate_images_openai.py --model gpt-image-2 --size 1024x1536
```

## 输出

分镜图片：

```text
assets/images/ep001/s01.png
assets/images/ep001/s02.png
assets/images/ep001/s03.png
...
```

实际使用的 prompt 记录：

```text
outputs/ep001/image_prompts_used.json
```

总览图：

```text
outputs/ep001/contact_sheet.jpg
```

如果某个 shot 的 `image_prompt` 为空，脚本会用 `visual`、`character_action` 和 episode 顶层 `style` 自动拼成 prompt。

## 角色参考库

第一集确认后的 Zero-One 角色参考图保存在：

```text
assets/reference/characters/zero_one/zero_one_ep001_s02.png
```

后续剧集生成 Zero-One 角色镜头时，优先把这张图作为唯一角色参考：

```powershell
python scripts/generate_images_openai.py --shot-ids s03,s04 --force --quality low --reference-image assets/reference/characters/zero_one/zero_one_ep001_s02.png
```

`--shot-ids` 只重生成指定分镜；`--reference-image` 会把参考图传给 OpenAI Images Edit 接口，用来稳定角色形象。

## 图片到最终成片

第一版成片流水线分为四步：

```powershell
python scripts/prepare_video_refs.py episodes/ep001_moon_pink.json --force
python scripts/generate_videos_openai.py episodes/ep001_moon_pink.json --model sora-2 --size 720x1280 --seconds 8
python scripts/generate_voice_openai.py episodes/ep001_moon_pink.json
python scripts/assemble_final_video.py episodes/ep001_moon_pink.json
```

输出路径：

```text
outputs/ep001/video_refs/
outputs/ep001/clips/
outputs/ep001/audio/
outputs/ep001/final/ep001_final.mp4
```

`generate_videos_openai.py` 会把每个分镜图作为 Sora 输入参考图，生成独立视频片段。`generate_voice_openai.py` 会按 `voice` 字段生成每条台词的音频。`assemble_final_video.py` 会把视频裁到分镜时长、配音、拼接并烧录字幕。
