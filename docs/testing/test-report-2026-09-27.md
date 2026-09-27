# Independent Test Report - OmniStack ShortForm Studio MVP (P2 TEST)

- Date: 2026-09-27
- Verifier: `tester` (adversarial), independent of the developer
- Repo: `/opt/workspace/shortform-studio`
- Branch: `main`
- HEAD at test time: `a75f71006a902c14cc4df888b38151f2f7eda153`
- `origin/main` at test time: `a75f71006a902c14cc4df888b38151f2f7eda153`
- Working tree before test: clean (`git status --short` empty)
- Tooling: Python 3.11.2; ffmpeg 5.1.9-0+deb12u1; pytest 7.2.1
- Artifact under test: `out/roman-concrete/video.mp4` + title/description/metadata/provenance/qa/ffprobe/captions/graphics

Every criterion below was **re-run from scratch by the verifier** with raw commands. The
developer's prose and committed `out/selftest/*` logs were not trusted; only raw command output
is reported. All commands were run with the repo as the working directory.

## Verdict summary

| AC | Criterion | Verdict |
|----|-----------|---------|
| AC1 | PRODUCED (ffprobe + non-silent audio) | **PASS** |
| AC2 | LOUDNESS (-14 +/-1 LUFS, TP <= -1 dBTP) | **PASS** |
| AC3 | POLICY/QA + originality/provenance | **PASS** |
| AC4 | UPLOAD PATH (dry-run shape, own mock live, exit-2 handover) | **PASS** |
| AC5 | MEASUREMENT (mock + jsonl + live URL shape) | **PASS** |
| AC6 | REPRODUCIBILITY (delete-and-regenerate, new slug) | **PASS** |
| AC7 | TESTS (pytest) | **PASS** |

**Final verdict: APPROVE-READY (7/7 PASS).** Non-blocking findings and untested scope are listed
under "Findings, UNKNOWNs and limitations".

---

## AC1 PRODUCED - ffprobe of the artifact + proof the audio is not silent

### AC1.1 ffprobe (run by the verifier)

```
$ ffprobe -v error -show_streams -show_format -of json out/roman-concrete/video.mp4
```

Raw output (full):

```json
{
    "streams": [
        {
            "index": 0,
            "codec_name": "h264",
            "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            "profile": "Constrained Baseline",
            "codec_type": "video",
            "codec_tag_string": "avc1",
            "codec_tag": "0x31637661",
            "width": 1080,
            "height": 1920,
            "coded_width": 1080,
            "coded_height": 1920,
            "closed_captions": 0,
            "film_grain": 0,
            "has_b_frames": 0,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "9:16",
            "pix_fmt": "yuv420p",
            "level": 40,
            "chroma_location": "left",
            "field_order": "progressive",
            "refs": 1,
            "is_avc": "true",
            "nal_length_size": "4",
            "id": "0x1",
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "time_base": "1/15360",
            "start_pts": 0,
            "start_time": "0.000000",
            "duration_ts": 576000,
            "duration": "37.500000",
            "bit_rate": "358714",
            "bits_per_raw_sample": "8",
            "nb_frames": "1125",
            "extradata_size": 40,
            "disposition": {
                "default": 1,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0
            },
            "tags": {
                "language": "und",
                "handler_name": "VideoHandler",
                "vendor_id": "[0][0][0][0]",
                "encoder": "Lavc59.37.100 libx264"
            }
        },
        {
            "index": 1,
            "codec_name": "aac",
            "codec_long_name": "AAC (Advanced Audio Coding)",
            "profile": "LC",
            "codec_type": "audio",
            "codec_tag_string": "mp4a",
            "codec_tag": "0x6134706d",
            "sample_fmt": "fltp",
            "sample_rate": "48000",
            "channels": 2,
            "channel_layout": "stereo",
            "bits_per_sample": 0,
            "id": "0x2",
            "r_frame_rate": "0/0",
            "avg_frame_rate": "0/0",
            "time_base": "1/48000",
            "start_pts": 0,
            "start_time": "0.000000",
            "duration_ts": 1800000,
            "duration": "37.500000",
            "bit_rate": "146784",
            "nb_frames": "1759",
            "extradata_size": 5,
            "disposition": {
                "default": 1,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0
            },
            "tags": {
                "language": "und",
                "handler_name": "SoundHandler",
                "vendor_id": "[0][0][0][0]"
            }
        },
        {
            "index": 2,
            "codec_name": "mov_text",
            "codec_long_name": "MOV text",
            "codec_type": "subtitle",
            "codec_tag_string": "tx3g",
            "codec_tag": "0x67337874",
            "id": "0x3",
            "r_frame_rate": "0/0",
            "avg_frame_rate": "0/0",
            "time_base": "1/1000000",
            "start_pts": 0,
            "start_time": "0.000000",
            "duration_ts": 37500000,
            "duration": "37.500000",
            "bit_rate": "101",
            "nb_frames": "7",
            "extradata_size": 68,
            "disposition": {
                "default": 1,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0
            },
            "tags": {
                "language": "und",
                "handler_name": "SubtitleHandler"
            }
        }
    ],
    "format": {
        "filename": "out/roman-concrete/video.mp4",
        "nb_streams": 3,
        "nb_programs": 0,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "format_long_name": "QuickTime / MOV",
        "start_time": "0.000000",
        "duration": "37.500000",
        "size": "2404763",
        "bit_rate": "513016",
        "probe_score": 100,
        "tags": {
            "major_brand": "isom",
            "minor_version": "512",
            "compatible_brands": "isomiso2avc1mp41",
            "encoder": "Lavf59.27.100"
        }
    }
}
```

```
$ ffprobe -v error -show_entries stream=codec_type -of csv=p=0 out/roman-concrete/video.mp4 | sort | uniq -c
      1 audio
      1 subtitle
      1 video
```

```
$ ffprobe -v error -select_streams v:0 -show_entries stream=codec_type,codec_name,width,height,pix_fmt,sample_aspect_ratio,display_aspect_ratio,r_frame_rate,duration -of default=noprint_wrappers=1 out/roman-concrete/video.mp4
codec_name=h264
codec_type=video
width=1080
height=1920
sample_aspect_ratio=1:1
display_aspect_ratio=9:16
pix_fmt=yuv420p
r_frame_rate=30/1
duration=37.500000
```

```
$ ffprobe -v error -select_streams a:0 -show_entries stream=codec_type,codec_name,sample_rate,channels,channel_layout -of default=noprint_wrappers=1 out/roman-concrete/video.mp4
codec_name=aac
codec_type=audio
sample_rate=48000
channels=2
channel_layout=stereo
```

Assessment: exactly **one** video stream (h264, 1080x1920, yuv420p, SAR 1:1, 9:16), one real
**aac** audio stream (48 kHz stereo), plus one `mov_text` subtitle stream. Format duration
**37.500 s**, inside 15-60 s.

### AC1.2 Non-silent audio - volumedetect

```
$ ffmpeg -hide_banner -i out/roman-concrete/video.mp4 -af volumedetect -f null -
```

Raw tail (the measurement lines):

```
[Parsed_volumedetect_0 @ 0x564cce0ff7c0] n_samples: 3600384
[Parsed_volumedetect_0 @ 0x564cce0ff7c0] mean_volume: -18.4 dB
[Parsed_volumedetect_0 @ 0x564cce0ff7c0] max_volume: -1.3 dB
[Parsed_volumedetect_0 @ 0x564cce0ff7c0] histogram_1db: 2452
[Parsed_volumedetect_0 @ 0x564cce0ff7c0] histogram_2db: 6642
```

Assessment: `mean_volume = -18.4 dB`, `max_volume = -1.3 dB` which is **> -40 dB**. The audio is
real and non-silent; 3,600,384 samples were analysed.

**AC1: PASS.**

---

## AC2 LOUDNESS - integrated loudness and true peak

### AC2.1 Exact command from the brief

```
$ ffmpeg -hide_banner -nostats -i out/roman-concrete/video.mp4 -af loudnorm=print_format=json -f null -
```

Raw JSON:

```json
{
	"input_i" : "-14.44",
	"input_tp" : "-1.28",
	"input_lra" : "7.00",
	"input_thresh" : "-24.50",
	"output_i" : "-24.03",
	"output_tp" : "-9.26",
	"output_lra" : "3.40",
	"output_thresh" : "-34.06",
	"normalization_type" : "dynamic",
	"target_offset" : "0.03"
}
```

### AC2.2 Target-aware re-measure (same file, explicit I/TP for clarity)

```
$ ffmpeg -hide_banner -nostats -i out/roman-concrete/video.mp4 -af loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json -f null -
```

Raw JSON:

```json
{
	"input_i" : "-14.44",
	"input_tp" : "-1.28",
	"input_lra" : "7.00",
	"input_thresh" : "-24.50",
	"output_i" : "-14.20",
	"output_tp" : "-1.50",
	"output_lra" : "3.30",
	"output_thresh" : "-24.23",
	"normalization_type" : "dynamic",
	"target_offset" : "0.20"
}
```

Assessment: measured integrated loudness `input_i = -14.44 LUFS`, inside `-14 +/-1`. Measured
true peak `input_tp = -1.28 dBTP <= -1.0 dBTP`. `qa` independently re-measures with ebur128 and
reports `integrated=-14.4 LUFS`, `true_peak=-1.3 dBTP` (see AC3), consistent with the above.

**AC2: PASS.**

---

## AC3 POLICY/QA - qa exit code + copy/metadata + originality/provenance

### AC3.1 Re-run qa

```
$ python3 -m shortform qa --slug roman-concrete
[PASS] video_exists: /opt/workspace/shortform-studio/out/roman-concrete/video.mp4
[PASS] duration_15_60s: duration=37.500s (required 15-60s)
[PASS] video_codec_h264: codec_name='h264' (required h264)
[PASS] pixel_format_yuv420p: pix_fmt='yuv420p' (required yuv420p)
[PASS] resolution_1080x1920: resolution=1080x1920 (required 1080x1920)
[PASS] sar_1_1: sample_aspect_ratio='1:1' (required 1:1)
[PASS] audio_aac: audio codec='aac' (required aac)
[PASS] integrated_loudness_-14_plusminus_1: integrated=-14.4 LUFS (required -14 +/-1)
[PASS] true_peak_le_-1_dbtp: true_peak=-1.3 dBTP (required <= -1.0)
[PASS] title_le_100_chars: title length=38 (required 1-100)
[PASS] description_le_5000_chars: description length=518 (required 1-5000)
[PASS] shorts_hashtag_present: #Shorts present in description
[PASS] synthetic_media_disclosure: AI/synthetic-media disclosure sentence present
[PASS] urls_well_formed: no malformed URLs
[PASS] affiliate_disclosure_when_needed: no affiliate link present
[PASS] metadata_selfDeclaredMadeForKids_false: selfDeclaredMadeForKids=False (required false)
[PASS] metadata_synthetic_disclosure_flag: synthetic-media disclosure flag present in metadata
QA RESULT: PASS
QA_EXIT_CODE=0
```

### AC3.2 Independent policy assertions (verifier's own code, not the qa module)

```
$ python3 - <<'PY'
import json
from pathlib import Path
desc = Path("out/roman-concrete/description.txt").read_text("utf-8")
title = Path("out/roman-concrete/title.txt").read_text("utf-8").strip()
meta = json.loads(Path("out/roman-concrete/metadata.json").read_text("utf-8"))
disclosure = ("This video contains synthetic media: the narration is machine-generated and "
              "the visuals are computer-generated by shortform-studio. No third-party "
              "footage, music, or images were used.")
print("desc_len =", len(desc), "<=5000 ->", len(desc) <= 5000)
print("title_len =", len(title), "<=100 ->", len(title) <= 100)
print("#Shorts in desc ->", "#Shorts" in desc)
print("disclosure sentence in desc ->", disclosure in desc)
print("selfDeclaredMadeForKids == False ->", meta["status"]["selfDeclaredMadeForKids"] is False,
      "| top-level:", meta.get("selfDeclaredMadeForKids"))
print("containsSyntheticMedia ->", meta["status"].get("containsSyntheticMedia"))
print("syntheticMediaDisclosure ->", meta.get("syntheticMediaDisclosure"))
PY
```

Raw output:

```
desc_len = 518 <=5000 -> True
title_len = 38 <=100 -> True
#Shorts in desc -> True
disclosure sentence in desc -> True
selfDeclaredMadeForKids == False -> True | top-level: False
containsSyntheticMedia -> True
syntheticMediaDisclosure -> True
```

The independent readings agree with the qa module: `#Shorts` present, the exact synthetic-media
disclosure sentence present, description 518 <= 5000, title 38 <= 100,
`selfDeclaredMadeForKids=false` (both top-level and under `status`), synthetic-media disclosure
flag present (`status.containsSyntheticMedia=true` and `syntheticMediaDisclosure=true`).

### AC3.3 Originality / provenance - only locally generated assets, no third-party URL

Verifier command (lists the asset inputs and asserts no external URL):

```
$ python3 - <<'PY'
import json, re
from pathlib import Path
script = json.loads(Path("content/roman-concrete/script.json").read_text("utf-8"))
print("narration scenes:", len(script["narration"]))
for s in script["narration"]:
    print("  scene", s["scene"], "say:", s["say"])
prov = json.loads(Path("out/roman-concrete/provenance.json").read_text("utf-8"))
print("provenance inputs:")
for i in prov["inputs"]:
    print("  ", i)
blob = (Path("out/roman-concrete/provenance.json").read_text("utf-8")
        + Path("content/roman-concrete/script.json").read_text("utf-8"))
urls = re.findall(r"https?://[^\s\"'<>]+", blob)
print("URLs found in script+provenance:", urls)
bad = [o["path"] for o in prov["outputs"]
       if not str(o["path"]).startswith("/opt/workspace/shortform-studio/")]
print("non-local output paths:", bad)
PY
```

Raw output:

```
narration scenes: 6
narration text:
  scene 1 say: Rome's harbour walls have taken two thousand years of salt and storm, and many are still standing.
  scene 2 say: Modern concrete poured for the same job can crack apart in fifty.
  scene 3 say: The Roman recipe was volcanic ash, quicklime, and seawater.
  scene 4 say: That mixture slowly grew rare crystals, aluminous tobermorite, that knitted the mortar together.
  scene 5 say: The salt that rusts modern steel was actually feeding the Roman chemistry.
  scene 6 say: Engineers now study those ancient recipes to design concrete that lasts.
provenance inputs:
   {'role': 'script', 'path': '/opt/workspace/shortform-studio/content/roman-concrete/script.json', 'sha256': 'b79fcb318beb925a92cf649c5456f78e8661f5589b390b364c3639f404067bf0', 'sha256_text': 'b79fcb318beb925a92cf649c5456f78e8661f5589b390b364c3639f404067bf0'}
URLs found in script+provenance: []
non-local output paths: []
```

The provenance hash binds to the real script, verified independently:

```
$ python3 -c "import hashlib,json; p='content/roman-concrete/script.json'; real=hashlib.sha256(open(p,'rb').read()).hexdigest(); prov=json.load(open('out/roman-concrete/provenance.json')); print('real   ',real); print('provenance', prov['inputs'][0]['sha256']); print('MATCH', real==prov['inputs'][0]['sha256'])"
real    b79fcb318beb925a92cf649c5456f78e8661f5589b390b364c3639f404067bf0
provenance b79fcb318beb925a92cf649c5456f78e8661f5589b390b364c3639f404067bf0
MATCH True
```

The sole provenance **input** is the local `content/roman-concrete/script.json`; every output path
is inside the repo; the narration is original prose; **zero** external/third-party URLs appear in
either file. Provenance `tools`/`commands` record only local `ffmpeg`/`ffprobe`/`espeak-ng`
invocations.

**AC3: PASS.**

---

## AC4 UPLOAD PATH

No Google sandbox/credential exists in this environment (confirmed: no `YOUTUBE_*`/`GOOGLE_*`
env vars are set). The live leg is therefore driven against the bundled local mock, exactly as
the brief permits. Because `publish --live` demands a token before it will open a socket, the mock
leg was run with a **non-secret dummy token** so the live code path could execute; the mock does
not validate tokens and the token is redacted in its transcript.

### AC4a Dry-run request shape

```
$ python3 -m shortform publish --slug roman-concrete --dry-run
=== DRY RUN (no network request is sent) ===
STEP 1: https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status  [METHOD: POST]
Headers:
  Authorization: Bearer <redacted:29 chars>
  Content-Type: application/json; charset=UTF-8
  X-Upload-Content-Type: video/mp4
  X-Upload-Content-Length: 2404763
Body:
{
  "snippet": {
    "title": "How Roman Concrete Survived 2000 Years",
    "description": "How Roman Concrete Survived 2000 Years\n\nRoman harbour concrete has outlasted two thousand years of salt and storm, while modern concrete often fails within decades. This short explains the volcanic-ash recipe that let seawater grow strengthening minerals inside Roman mortar.\n\nThis video contains synthetic media: the narration is machine-generated and the visuals are computer-generated by shortform-studio. No third-party footage, music, or images were used.\n\n#Shorts #RomanConcrete #Engineering #History #Materials\n",
    "tags": [
      "roman concrete",
      "ancient rome",
      "engineering",
      "materials science",
      "history",
      "shorts"
    ],
    "categoryId": "27"
  },
  "status": {
    "privacyStatus": "private",
    "selfDeclaredMadeForKids": false,
    "containsSyntheticMedia": true,
    "license": "youtube",
    "embeddable": true
  }
}

STEP 2: PUT <Location returned by step 1>
Headers:
  Content-Type: video/mp4
  Content-Length: 2404763
Body: <2404763 bytes of /opt/workspace/shortform-studio/out/roman-concrete/video.mp4>

DRY RUN COMPLETE - nothing was uploaded.
DRYRUN_EXIT_CODE=0
```

Assessment: real resumable-upload shape. `POST
https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status`;
`Authorization: Bearer ...`; `X-Upload-Content-Type: video/mp4`;
`X-Upload-Content-Length: 2404763` (= the exact bytes of `video.mp4`); body
`status.privacyStatus=private`, `status.selfDeclaredMadeForKids=false`. **PASS.**

Extra falsification (proves "sends nothing"): the dry-run was pointed at a **live** mock and the
mock's transcript contained only `SESSION START`:

```
$ YOUTUBE_OAUTH_TOKEN=ya29.secret-dryrun-token python3 -m shortform publish --slug roman-concrete --dry-run --api-base http://127.0.0.1:8790
DRYRUN_EXIT_CODE=0
--- mock transcript (should contain ONLY SESSION START, no REQUEST) ---
2026-09-27T04:25:50Z pid=9390 SESSION START mock listening on http://127.0.0.1:8790 transcript=/tmp/p2-evidence/mock-dryrun.log
--- request count: 0 ---
```

### AC4b Verifier's OWN live upload through a freshly started mock on port 8790

Mock started by the verifier (transcript written to `/tmp`, so the tracked `mocks/transcript.log`
is not modified):

```
$ python3 mocks/youtube_mock.py --port 8790 --transcript /tmp/p2-evidence/mock-ac4b.log &
[mock] YouTube mock listening on http://127.0.0.1:8790
[mock] transcript -> /tmp/p2-evidence/mock-ac4b.log

$ YOUTUBE_OAUTH_TOKEN="ya29.dummy-token-for-local-mock-0001" \
    python3 -m shortform publish --slug roman-concrete --live --api-base http://127.0.0.1:8790
POST http://127.0.0.1:8790/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status
  -> session Location: http://127.0.0.1:8790/upload-session/d934e790f2ee48dca8e53b545fed3f2c
PUT http://127.0.0.1:8790/upload-session/d934e790f2ee48dca8e53b545fed3f2c (2404763 bytes)
UPLOAD OK id=MOCKID123 privacy=private
LIVE_EXIT_CODE=0
```

The mock's **raw request/response transcript for the verifier's own run** (single instance,
pid 9131):

```
2026-09-27T04:24:22Z pid=9131 SESSION START mock listening on http://127.0.0.1:8790 transcript=/tmp/p2-evidence/mock-ac4b.log
2026-09-27T04:24:23Z pid=9131 REQUEST POST /upload/youtube/v3/videos?uploadType=resumable&part=snippet,status HTTP/1.1
2026-09-27T04:24:23Z pid=9131   Accept-Encoding: identity
2026-09-27T04:24:23Z pid=9131   Content-Length: 877
2026-09-27T04:24:23Z pid=9131   Host: 127.0.0.1:8790
2026-09-27T04:24:23Z pid=9131   User-Agent: Python-urllib/3.11
2026-09-27T04:24:23Z pid=9131   Authorization: Bearer <redacted:36 chars>
2026-09-27T04:24:23Z pid=9131   Content-Type: application/json; charset=UTF-8
2026-09-27T04:24:23Z pid=9131   X-Upload-Content-Type: video/mp4
2026-09-27T04:24:23Z pid=9131   X-Upload-Content-Length: 2404763
2026-09-27T04:24:23Z pid=9131   Connection: close
2026-09-27T04:24:23Z pid=9131   BODY '{"snippet": {"title": "How Roman Concrete Survived 2000 Years", "description": "How Roman Concrete Survived 2000 Years\\n\\nRoman harbour concrete has outlasted two thousand years of salt and storm, while modern concrete often fails within decades. This short explains the volcanic-ash recipe that let seawater grow strengthening minerals inside Roman mortar.\\n\\nThis video contains synthetic media: the narration is machine-generated and the visuals are computer-generated by shortform-studio. No third-party footage, music, or images were used.\\n\\n#Shorts #RomanConcrete #Engineering #History #Materials\\n", "tags": ["roman concrete", "ancient rome", "engineering", "materials science", "history", "shorts"], "categoryId": "27"}, "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": false, "containsSyntheticMedia": true, "license": "youtube", "embeddable": true}}' (877 bytes)
2026-09-27T04:24:23Z pid=9131 RESPONSE 200 {'Location': 'http://127.0.0.1:8790/upload-session/d934e790f2ee48dca8e53b545fed3f2c', 'X-GUploader-UploadID': 'd934e790f2ee48dca8e53b545fed3f2c'} body=47 bytes
2026-09-27T04:24:23Z pid=9131 REQUEST PUT /upload-session/d934e790f2ee48dca8e53b545fed3f2c HTTP/1.1
2026-09-27T04:24:23Z pid=9131   Accept-Encoding: identity
2026-09-27T04:24:23Z pid=9131   Host: 127.0.0.1:8790
2026-09-27T04:24:23Z pid=9131   User-Agent: Python-urllib/3.11
2026-09-27T04:24:23Z pid=9131   Content-Type: video/mp4
2026-09-27T04:24:23Z pid=9131   Content-Length: 2404763
2026-09-27T04:24:23Z pid=9131   Connection: close
2026-09-27T04:24:23Z pid=9131   RECEIVED 2404763 video bytes (sha256-free mock); first4=b'\x00\x00\x00 '
2026-09-27T04:24:23Z pid=9131 RESPONSE 200 {} body=198 bytes
```

`video.mp4` actual size was independently measured as **2404763 bytes**; the `X-Upload-Content-Length`
and the `PUT Content-Length` and the `RECEIVED` count all match exactly. The returned video id is
`MOCKID123`. The written `publish-result.json` for this run:

```json
{
  "slug": "roman-concrete",
  "uploaded_at": "2026-09-27T04:24:23Z",
  "api_base": "http://127.0.0.1:8790",
  "privacy_status": "private",
  "http_status": 200,
  "video": "/opt/workspace/shortform-studio/out/roman-concrete/video.mp4",
  "bytes": 2404763,
  "video_id": "MOCKID123",
  "response": {
    "kind": "youtube#video",
    "etag": "mock-etag",
    "id": "MOCKID123",
    "snippet": {"title": "Mock Upload", "channelId": "MOCKCHANNEL"},
    "status": {"privacyStatus": "private", "uploadStatus": "uploaded"}
  }
}
```

(The mock was killed after the run. `out/roman-concrete/publish-result.json` was restored to the
committed revision before committing this report, so the repo is not polluted by the verifier's
run.) **PASS.**

### AC4c No-credential live publish -> exit 2, human handover, no upload claim

```
$ env -u YOUTUBE_OAUTH_TOKEN -u YOUTUBE_API_KEY python3 -m shortform publish --slug roman-concrete --live
PUBLISH_NO_CRED_EXIT_CODE=2
--- stdout ---
(empty)
--- stderr ---
[HUMAN HANDOVER REQUIRED] Cannot publish live: $YOUTUBE_OAUTH_TOKEN is not set.
No upload was attempted and nothing was faked.

To enable a live upload a human must:
  1. In Google Cloud Console create/select a project and enable "YouTube Data API v3".
  2. Configure the OAuth consent screen (External, Testing is fine) and add the scope
     https://www.googleapis.com/auth/youtube.upload
  3. Create an OAuth 2.0 Client ID of type "Desktop app", then run the OAuth flow
     (for example `google-auth-oauthlib`'s InstalledAppFlow) to mint an access token.
  4. Export it for this shell and re-run:
       export YOUTUBE_OAUTH_TOKEN="ya29.<...>"
       python -m shortform publish --slug <slug> --live --privacy private
  5. Approve the upload in YouTube Studio; the default privacy is "private" on purpose.
```

Independent proof that nothing was claimed or written: `sha256(publish-result.json)` was identical
before and after the call.

```
sha256 publish-result.json BEFORE: 73b566ce5f3dfa665a7d6284dbe113a5aa1d147cab8a873fb07bd984f5899758
sha256 publish-result.json AFTER:  73b566ce5f3dfa665a7d6284dbe113a5aa1d147cab8a873fb07bd984f5899758
```

The message contains the explicit human-handover instructions and the explicit statement "No
upload was attempted and nothing was faked"; there is no `UPLOAD OK`/success claim. **PASS.**

**AC4: PASS.**

---

## AC5 MEASUREMENT

`measure --mock` defaults to `http://127.0.0.1:8787`, so the verifier started a mock there; a
second mock on 8790 exercised the explicit `--api-base` / non-mock branch. Both transcripts were
written under `/tmp`.

### AC5.1 `measure --mock`

```
$ python3 -m shortform measure --video-id MOCKID123 --mock
GET http://127.0.0.1:8787/youtube/v3/videos?part=snippet%2Cstatistics&id=MOCKID123&key=MOCK_KEY
title: How Roman concrete survived 2000 years #Shorts
views: 12874
likes: 1043
comments: 87
view_through_placeholder_pct: 8.784
snapshot appended to /opt/workspace/shortform-studio/data/metrics/MOCKID123.jsonl
MEASURE_MOCK_EXIT_CODE=0
```

Raw server transcript for this GET:

```
2026-09-27T04:24:39Z pid=9167 REQUEST GET /youtube/v3/videos?part=snippet%2Cstatistics&id=MOCKID123&key=MOCK_KEY HTTP/1.1
2026-09-27T04:24:39Z pid=9167 RESPONSE 200 {} body=466 bytes
```

### AC5.2 Explicit base on 8790 (non-mock source)

```
$ YOUTUBE_API_KEY=TESTKEY_123 python3 -m shortform measure --video-id MOCKID123 --api-base http://127.0.0.1:8790
GET http://127.0.0.1:8790/youtube/v3/videos?part=snippet%2Cstatistics&id=MOCKID123&key=TESTKEY_123
title: How Roman concrete survived 2000 years #Shorts
views: 12874
likes: 1043
comments: 87
view_through_placeholder_pct: 8.784
snapshot appended to /opt/workspace/shortform-studio/data/metrics/MOCKID123.jsonl
MEASURE_API_BASE_EXIT_CODE=0
```

Raw server transcript:

```
2026-09-27T04:24:39Z pid=9168 REQUEST GET /youtube/v3/videos?part=snippet%2Cstatistics&id=MOCKID123&key=TESTKEY_123 HTTP/1.1
2026-09-27T04:24:39Z pid=9168 RESPONSE 200 {} body=466 bytes
```

### AC5.3 Appended lines in `data/metrics/<id>.jsonl`

```
$ wc -l data/metrics/MOCKID123.jsonl
3 data/metrics/MOCKID123.jsonl
$ tail -n 3 data/metrics/MOCKID123.jsonl
{"fetched_at": "2026-09-27T04:21:09Z", "video_id": "MOCKID123", "source": "mock", "api_base": "http://127.0.0.1:8787", "title": "How Roman concrete survived 2000 years #Shorts", "channelTitle": "OmniStack Mock Channel", "statistics": {"viewCount": "12874", "likeCount": "1043", "favoriteCount": "0", "commentCount": "87"}, "view_through_placeholder_pct": 8.784, "view_through_note": "Placeholder derived from public likes/comments/views; the real view-through rate requires the YouTube Analytics API (OAuth)."}
{"fetched_at": "2026-09-27T04:24:39Z", "video_id": "MOCKID123", "source": "mock", "api_base": "http://127.0.0.1:8787", "title": "How Roman concrete survived 2000 years #Shorts", "channelTitle": "OmniStack Mock Channel", "statistics": {"viewCount": "12874", "likeCount": "1043", "favoriteCount": "0", "commentCount": "87"}, "view_through_placeholder_pct": 8.784, "view_through_note": "Placeholder derived from public likes/comments/views; the real view-through rate requires the YouTube Analytics API (OAuth)."}
{"fetched_at": "2026-09-27T04:24:39Z", "video_id": "MOCKID123", "source": "youtube-data-api-v3", "api_base": "http://127.0.0.1:8790", "title": "How Roman concrete survived 2000 years #Shorts", "channelTitle": "OmniStack Mock Channel", "statistics": {"viewCount": "12874", "likeCount": "1043", "favoriteCount": "0", "commentCount": "87"}, "view_through_placeholder_pct": 8.784, "view_through_note": "Placeholder derived from public likes/comments/views; the real view-through rate requires the YouTube Analytics API (OAuth)."}
```

Both the `--mock` run and the explicit-base run appended a well-formed snapshot line.

### AC5.4 Live query URL shape

Constructed with the module's own `REAL_API_BASE` and the same `urlencode` call the code uses:

```
$ python3 - <<'PY'
from urllib.parse import urlencode, urlparse, parse_qs
from shortform import measure
q = urlencode({"part": "snippet,statistics", "id": "MOCKID123", "key": "API_KEY"})
url = f"{measure.REAL_API_BASE.rstrip('/')}/youtube/v3/videos?{q}"
print("REAL_API_BASE =", measure.REAL_API_BASE)
print("constructed URL =", url)
p = urlparse(url)
print("path =", p.path)
print("decoded query params =", parse_qs(p.query))
PY
REAL_API_BASE = https://www.googleapis.com
constructed URL = https://www.googleapis.com/youtube/v3/videos?part=snippet%2Cstatistics&id=MOCKID123&key=API_KEY
path = /youtube/v3/videos
decoded query params = {'part': ['snippet,statistics'], 'id': ['MOCKID123'], 'key': ['API_KEY']}
```

Assessment: the live URL is
`https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id=<ID>&key=<API_KEY>`.
The only difference from the brief's literal string is standard percent-encoding of the comma in
`part=snippet%2Cstatistics`; decoded, the parameters are exactly `part=snippet,statistics`,
`id=MOCKID123`, `key=API_KEY`. **PASS.**

Extra: the no-key live branch exits 2 with a human-handover message and sends nothing:

```
$ env -u YOUTUBE_API_KEY python3 -m shortform measure --video-id MOCKID123
MEASURE_NO_KEY_EXIT_CODE=2
--- stderr ---
[HUMAN HANDOVER REQUIRED] Cannot measure against the real API: $YOUTUBE_API_KEY is not set.
No request was sent.
...
```

**AC5: PASS.**

---

## AC6 REPRODUCIBILITY - delete-and-regenerate under a new slug

```
$ rm -rf content/test-repro out/test-repro
$ mkdir -p content/test-repro
$ cp content/roman-concrete/script.json content/test-repro/script.json
input script sha256: b79fcb318beb925a92cf649c5456f78e8661f5589b390b364c3639f404067bf0

$ python3 -m shortform produce --slug test-repro
PRODUCE_EXIT_CODE=0
produced /opt/workspace/shortform-studio/out/test-repro/video.mp4 (37.500s, 6 scenes)
provenance: /opt/workspace/shortform-studio/out/test-repro/provenance.json

$ python3 -m shortform qa --slug test-repro
QA_EXIT_CODE=0
[PASS] video_exists: /opt/workspace/shortform-studio/out/test-repro/video.mp4
[PASS] duration_15_60s: duration=37.500s (required 15-60s)
[PASS] video_codec_h264: codec_name='h264' (required h264)
[PASS] pixel_format_yuv420p: pix_fmt='yuv420p' (required yuv420p)
[PASS] resolution_1080x1920: resolution=1080x1920 (required 1080x1920)
[PASS] sar_1_1: sample_aspect_ratio='1:1' (required 1:1)
[PASS] audio_aac: audio codec='aac' (required aac)
[PASS] integrated_loudness_-14_plusminus_1: integrated=-14.4 LUFS (required -14 +/-1)
[PASS] true_peak_le_-1_dbtp: true_peak=-1.3 dBTP (required <= -1.0)
[PASS] title_le_100_chars: title length=38 (required 1-100)
[PASS] description_le_5000_chars: description length=518 (required 1-5000)
[PASS] shorts_hashtag_present: #Shorts present in description
[PASS] synthetic_media_disclosure: AI/synthetic-media disclosure sentence present
[PASS] urls_well_formed: no malformed URLs
[PASS] affiliate_disclosure_when_needed: no affiliate link present
[PASS] metadata_selfDeclaredMadeForKids_false: selfDeclaredMadeForKids=False (required false)
[PASS] metadata_synthetic_disclosure_flag: synthetic-media disclosure flag present in metadata
QA RESULT: PASS

$ ffprobe -v error -show_entries format=duration -show_entries stream=codec_type,codec_name,width,height,pix_fmt,sample_aspect_ratio -of default=noprint_wrappers=1 out/test-repro/video.mp4
codec_name=h264
codec_type=video
width=1080
height=1920
sample_aspect_ratio=1:1
pix_fmt=yuv420p
codec_name=aac
codec_type=audio
codec_name=mov_text
codec_type=subtitle
width=N/A
height=N/A
duration=37.500000
```

Extra determinism check: the regenerated artifact is **byte-identical** to the committed one.

```
$ sha256sum out/roman-concrete/video.mp4 out/test-repro/video.mp4
9ce0e04ef5fe79fb27ec10fd2eb16efedc024b9dbe48d1c62827b45f8dfff206  out/roman-concrete/video.mp4
9ce0e04ef5fe79fb27ec10fd2eb16efedc024b9dbe48d1c62827b45f8dfff206  out/test-repro/video.mp4
$ cmp -s out/roman-concrete/video.mp4 out/test-repro/video.mp4 && echo "video.mp4 IDENTICAL (cmp)"
video.mp4 IDENTICAL (cmp)
title.txt IDENTICAL
description.txt IDENTICAL
metadata.json IDENTICAL
captions.srt IDENTICAL
```

`content/test-repro/` and `out/test-repro/` were deleted after the run and are **not** committed.

**AC6: PASS.**

---

## AC7 TESTS

```
$ python3 -m pytest -q tests/
.............                                                            [100%]
13 passed in 0.15s
PYTEST_EXIT_CODE=0
```

13 tests passed, 0 failures/errors.

**AC7: PASS.**

---

## Findings, UNKNOWNs and limitations

### Non-blocking findings (do not affect any AC verdict)

- **F1 (cosmetic, dry-run):** When no `YOUTUBE_OAUTH_TOKEN` is set, the dry-run prints
  `Authorization: Bearer <redacted:29 chars>`. The "29 chars" is the length of the literal
  placeholder `<YOUTUBE_OAUTH_TOKEN NOT SET>`, which `_redact_headers()` redacts just like a real
  token. It is harmless (no secret is present or leaked) but misleading: an operator cannot tell
  from the dry-run output whether a token is configured. The criterion still passes because a
  well-formed `Authorization: Bearer ...` header is shown. (`shortform/publish.py`
  `_redact_headers`.)
- **F2 (robustness):** Network failures that are not HTTP errors are uncaught. With an API key set
  and a dead host, `measure` prints the constructed URL and then dies with a raw
  `urllib.error.URLError: <urlopen error [Errno 111] Connection refused>` traceback (exit 1):
  ```
  $ YOUTUBE_API_KEY=TESTKEY python3 -m shortform measure --video-id MOCKID123 --api-base http://127.0.0.1:9999
  EXIT_CODE=1
  stderr tail:
  urllib.error.URLError: <urlopen error [Errno 111] Connection refused>
  ```
  `measure._get` catches only `HTTPError`; `publish._http` likewise; `cli.main` catches only
  `FileNotFoundError`/`ValueError`/`RuntimeError`. A clean `RuntimeError`/exit 3 would be better.
  This does not affect the offline mock criteria (AC5) because the mock was running.

### Scope limitations / UNKNOWNs (inherent to the environment, explicitly accepted by the brief)

- **U1:** The real Google `videos.insert` and `videos.list` endpoints were never contacted. There
  is no Google sandbox or credential here and no network path was used. AC4 is verified via the
  dry-run wire shape, the local mock round-trip, and the exit-2 handover; AC5's live URL shape is
  verified by construction from the module's own `REAL_API_BASE` plus a real GET against the mock
  through the non-mock code branch. A true live upload remains unverified by design.
- **U2:** The brief's claim that the repo is "pushed" cannot be confirmed from this offline
  environment. Local evidence: `origin` is configured
  (`https://github.com/nexuslbs/shortform-studio.git`), `main` tracks `origin/main`, and
  `git rev-parse HEAD == git rev-parse origin/main == a75f71006a902c14cc4df888b38151f2f7eda153`
  with no ahead/behind. Whether the remote server actually holds that commit is not verifiable
  without network access.
- **U3:** The pytest suite (13 tests) deliberately does not re-encode a full video; the E2E encode
  path is covered by `scripts/selftest.sh` and was independently re-exercised here under AC6.

### Secret hygiene

`git grep` over all tracked files for `ya29.`, `AIza...`, private-key blocks, `client_secret`,
`refresh_token` found only documentation placeholders (`ya29.<...>` in `README`/`RUNBOOK`/docstrings),
no real credential. No `YOUTUBE_OAUTH_TOKEN`/`YOUTUBE_API_KEY` was set in the verifier environment.
The mock transcript redacts Authorization headers.

---

## Final verdict

All seven acceptance criteria were independently reproduced with raw commands and raw outputs.

**APPROVE-READY.**
