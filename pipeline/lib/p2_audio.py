# Vendored from the private production pipeline (syllabus2anki).
# Logic UNCHANGED except: (1) WS data-dir override via S2A_DATA_DIR,
# (2) tolerant/overridable data-file loads (S2A_ENTRIES / S2A_AUDIO_MAP_OUT).
# Regression-verified byte-identical against production outputs. See docs/pipeline.md.
# -*- coding: utf-8 -*-
"""
P2 补音频：为全量 7809 张卡准备英美发音

输出：
  audio_raw/<yd_word>_uk.mp3  原始下载
  audio32/<yd_word>_uk.mp3    32kbps 单声道（约 5KB/条）
  audio_map2.json             {卡片 word → {uk: 文件名, us: 文件名}}
断点续跑：已存在且 >800 字节的跳过。
"""
import json, os, re, subprocess, sys, time, urllib.parse
import threading, concurrent.futures as cf
import requests

def _s2a_load(name, default):
    """Tolerant JSON load: missing/corrupt file -> default (keeps new-word runs lean)."""
    p = os.path.join(WS, name)
    if not os.path.exists(p):
        return default
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def _s2a_entries():
    d = _s2a_load(os.environ.get("S2A_ENTRIES", "entries_7619.json"), None)
    if d is None:
        return []
    if isinstance(d, list):
        return d
    return d.get("entries") or d.get("words") or []


WS = os.environ.get("S2A_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(WS, "audio_raw")
OUT = os.path.join(WS, "audio32")
os.makedirs(RAW, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

TL = threading.local()


def sess():
    if not hasattr(TL, "s"):
        TL.s = requests.Session()
        TL.s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
                             "Referer": "https://dict.youdao.com/"})
    return TL.s


def safe(w):
    for ch in '/\\:*?"<>| ':
        w = w.replace(ch, "_")
    return w.replace("'", "").replace("\u001f", "_")


def fname(word, typ):
    return "yd_" + safe(word).lower() + f"_{typ}.mp3"


def dl_speech(word, typ):
    """从 yd_cache 里取 ukspeech/usspeech"""
    import ydparse
    d = ydparse.load(word)
    if not d:
        return ""
    uk, us = ydparse.speech(d)
    return uk if typ == "uk" else us


def dl(word, typ, speech=""):
    fn = fname(word, typ)
    raw_p = os.path.join(RAW, fn)
    out_p = os.path.join(OUT, fn)
    if os.path.exists(out_p) and os.path.getsize(out_p) > 800:
        return fn
    if not (os.path.exists(raw_p) and os.path.getsize(raw_p) > 1500):
        s = speech or f"{word}&type={'1' if typ == 'uk' else '2'}"
        if "type=" not in s:
            s += "&type=1" if typ == "uk" else "&type=2"
        url = "https://dict.youdao.com/dictvoice?audio=" + urllib.parse.quote(s, safe="=&+")
        ok = False
        for a in range(3):
            try:
                r = sess().get(url, timeout=20)
                if r.status_code == 200 and len(r.content) > 1500:
                    open(raw_p, "wb").write(r.content)
                    ok = True
                    break
            except Exception:
                time.sleep(0.3 * (a + 1))
        if not ok:
            return ""
    # 压缩
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw_p,
                    "-ac", "1", "-ar", "22050", "-b:a", "32k", out_p],
                   capture_output=True)
    return fn if (os.path.exists(out_p) and os.path.getsize(out_p) > 800) else ""


def job(item):
    word, uk_s, us_s = item
    uk = dl(word, "uk", uk_s)
    us = dl(word, "us", us_s)
    return word, uk, us


def main():
    ents = _s2a_entries()
    items = []
    for e in ents:
        w = e["word"]
        items.append((w, dl_speech(w, "uk"), dl_speech(w, "us")))
    # 变体拼写不单独做音频（卡片上只显示文字标注）

    print("待处理卡片:", len(items), flush=True)
    res, done, fail = {}, 0, []
    t0 = time.time()
    with cf.ThreadPoolExecutor(10) as ex:
        for w, uk, us in ex.map(job, items):
            res[w] = {"uk": uk, "us": us}
            done += 1
            if not uk and not us:
                fail.append(w)
            if done % 500 == 0:
                print(f"{done}/{len(items)} 无音频={len(fail)} {time.time()-t0:.0f}s", flush=True)
    json.dump(res, open(os.environ.get("S2A_AUDIO_MAP_OUT") or os.path.join(WS, "audio_map2.json"), "w", encoding="utf-8"), ensure_ascii=False)
    ok = sum(1 for v in res.values() if v["uk"]) + sum(1 for v in res.values() if v["us"])
    print(f"完成：{ok} 条音频 / {len(items)*2} 目标，完全无音频的词 {len(fail)}")
    print("样例缺失:", fail[:20])
    tot = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT) if f.endswith(".mp3"))
    print("audio32 体积 MB:", round(tot / 1048576, 1), "文件数:", len(os.listdir(OUT)))


if __name__ == "__main__":
    main()
