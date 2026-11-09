#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_data.py — generate the SYNTHETIC mini20 demo dataset.

All definitions, examples and phrases below are hand-written fabrications for
demonstration — they imitate the dictionary cache JSON schema (see
pipeline/lib/ydparse.py) without containing any real dictionary content.
Regenerate with:  python gen_data.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
CACHE = os.path.join(DATA_DIR, "yd_cache")

# word -> demo content (all fabricated)
DATA = {
    "apple": dict(star=True, page=3, uk="ˈæp.l̩", us="ˈæp.l̩",
        senses=["n. 苹果；苹果树"], cstar=3,
        collins=[("N-COUNT", "可数名词", "苹果，一种常见的水果",
                  "The apple is one of the most popular fruits.", "苹果是最常见的水果之一。")],
        en=[("n.", "a round fruit with red, green or yellow skin")],
        blng=[("She picked a ripe apple from the tree.", "她从树上摘下一个成熟的苹果。")],
        phrs=[("apple of one's eye", "掌上明珠")],
        rels=[("applesauce", "苹果酱")]),
    "book": dict(star=True, page=3, uk="bʊk", us="bʊk",
        senses=["n. 书，书籍", "v. 预订，预约"], cstar=5,
        collins=[("N-COUNT", "可数名词", "书，著作",
                  "He is reading a book about history.", "他正在读一本历史书。"),
                 ("VERB", "动词", "预订", "I want to book a table for two.", "我想预订一张两人桌。")],
        en=[("n.", "a written work published in printed or electronic form"),
            ("v.", "to arrange to have a seat, room, etc. at a future time")],
        blng=[("I book a seat on the morning train every week.", "我每周都预订早班火车的座位。")],
        phrs=[("book review", "书评")], rels=[("booking", "预订")]),
    "river": dict(star=True, page=5, uk="ˈrɪv.ər", us="ˈrɪv.ɚ",
        senses=["n. 河，江"], cstar=4,
        collins=[("N-COUNT", "可数名词", "河流", "The river flows into the sea.", "这条河流入大海。")],
        en=[("n.", "a large natural flow of water")],
        blng=[("They built a small bridge across the river.", "他们在河上建了一座小桥。")],
        phrs=[], rels=[]),
    "quiet": dict(star=True, page=6, uk="ˈkwaɪ.ət", us="ˈkwaɪ.ət",
        senses=["adj. 安静的，平静的"], cstar=4,
        collins=[("ADJ", "形容词", "安静的", "Please keep quiet in the library.", "请在图书馆保持安静。")],
        en=[("adj.", "making little or no noise")],
        blng=[("The village is quiet at night.", "这个村庄夜晚很安静。")],
        phrs=[("keep quiet", "保持安静")], rels=[("quietly", "安静地")]),
    "bridge": dict(star=False, page=7, uk="brɪdʒ", us="brɪdʒ",
        senses=["n. 桥，桥梁"], cstar=3,
        collins=[("N-COUNT", "可数名词", "桥", "The old bridge was made of stone.", "这座旧桥是石头建的。")],
        en=[("n.", "a structure carrying a road across a river or other obstacle")],
        blng=[("A new bridge will connect the two towns.", "一座新桥将连接这两个城镇。")],
        phrs=[("build a bridge", "建桥")], rels=[]),
    "carry": dict(star=False, page=7, uk="ˈkær.i", us="ˈker.i",
        senses=["v. 携带，搬运"], cstar=4,
        collins=[("VERB", "动词", "搬运", "She carried a heavy box upstairs.", "她把一个重箱子搬上楼。")],
        en=[("v.", "to support and move something from one place to another")],
        blng=[("He helped me carry the bags to the car.", "他帮我把袋子搬到车上。")],
        phrs=[("carry out", "执行")], rels=[("carrier", "搬运工")]),
    "simple": dict(star=False, page=8, uk="ˈsɪm.pəl", us="ˈsɪm.pəl",
        senses=["adj. 简单的，容易的"], cstar=4,
        collins=[("ADJ", "形容词", "简单的", "The instructions are simple to follow.", "这些说明很容易照做。")],
        en=[("adj.", "easy to understand or do")],
        blng=[("It was a simple question with a clear answer.", "那是一个有明确答案的简单问题。")],
        phrs=[], rels=[("simply", "简单地")]),
    "wonder": dict(star=True, page=9, uk="ˈwʌn.dər", us="ˈwʌn.dɚ",
        senses=["v. 想知道，感到疑惑", "n. 惊奇，奇迹"], cstar=3,
        collins=[("VERB", "动词", "想知道", "I wonder why he left early.", "我想知道他为什么早退。")],
        en=[("v.", "to ask yourself questions about something"),
            ("n.", "a feeling of surprise and interest")],
        blng=[("She began to wonder what had happened.", "她开始想知道发生了什么。")],
        phrs=[("no wonder", "难怪")], rels=[("wonderful", "精彩的")]),
    "ocean": dict(star=True, page=10, uk="ˈəʊ.ʃən", us="ˈoʊ.ʃən",
        senses=["n. 海洋，大海"], cstar=3,
        collins=[("N-COUNT", "可数名词", "海洋", "The Pacific is the largest ocean.", "太平洋是最大的洋。")],
        en=[("n.", "the large body of salt water covering most of the earth")],
        blng=[("They sailed across the ocean last summer.", "去年夏天他们扬帆横渡大洋。")],
        phrs=[], rels=[]),
    "mountain": dict(star=False, page=11, uk="ˈmaʊn.tən", us="ˈmaʊn.tn",
        senses=["n. 山，高山"], cstar=3,
        collins=[("N-COUNT", "可数名词", "高山", "Snow covered the mountain all year.", "雪终年覆盖着这座山。")],
        en=[("n.", "a very high hill")],
        blng=[("We climbed the mountain in two days.", "我们用两天时间爬上了这座山。")],
        phrs=[("mountain range", "山脉")], rels=[]),
    "dream": dict(star=True, page=12, uk="driːm", us="driːm",
        senses=["n. 梦，梦想", "v. 做梦，梦见"], cstar=4,
        collins=[("N-COUNT", "可数名词", "梦", "I had a strange dream last night.", "我昨晚做了一个奇怪的梦。")],
        en=[("n.", "images and thoughts in your mind while you sleep"),
            ("v.", "to have images in your mind while sleeping")],
        blng=[("Her dream is to become a doctor.", "她的梦想是成为一名医生。")],
        phrs=[("dream come true", "梦想成真")], rels=[("dreamy", "梦幻般的")]),
    "learn": dict(star=True, page=13, uk="lɜːn", us="lɝːn",
        senses=["v. 学习，学会"], cstar=5,
        collins=[("VERB", "动词", "学习", "Children learn languages quickly.", "孩子学语言很快。")],
        en=[("v.", "to gain knowledge or skill by studying or practice")],
        blng=[("He wants to learn how to swim this year.", "他今年想学游泳。")],
        phrs=[("learn from", "向…学习")], rels=[("learner", "学习者")]),
    "city": dict(star=False, page=14, uk="ˈsɪt.i", us="ˈsɪt̬.i",
        senses=["n. 城市，都市"], cstar=5,
        collins=[("N-COUNT", "可数名词", "城市", "The city is famous for its parks.", "这座城市以公园闻名。")],
        en=[("n.", "a large important town")],
        blng=[("More people are moving to the city for work.", "更多人为了工作搬进这座城市。")],
        phrs=[], rels=[]),
    "music": dict(star=False, page=15, uk="ˈmjuː.zɪk", us="ˈmjuː.zɪk",
        senses=["n. 音乐，乐曲"], cstar=5,
        collins=[("N-UNCOUNT", "不可数名词", "音乐", "She listens to music every evening.", "她每晚都听音乐。")],
        en=[("n.", "sounds arranged in a pleasant way")],
        blng=[("The music filled the whole hall.", "音乐充满了整个大厅。")],
        phrs=[("pop music", "流行音乐")], rels=[("musical", "音乐的")]),
    "friend": dict(star=False, page=16, uk="frend", us="frend",
        senses=["n. 朋友，友人"], cstar=5,
        collins=[("N-COUNT", "可数名词", "朋友", "A good friend will always help you.", "好朋友总会帮助你。")],
        en=[("n.", "a person you know well and like")],
        blng=[("My friend and I study together on weekends.", "我和朋友周末一起学习。")],
        phrs=[("close friend", "密友")], rels=[("friendly", "友好的")]),
    "happy": dict(star=False, page=17, uk="ˈhæp.i", us="ˈhæp.i",
        senses=["adj. 快乐的，幸福的"], cstar=5,
        collins=[("ADJ", "形容词", "快乐的", "The news made everyone happy.", "这个消息让大家都很开心。")],
        en=[("adj.", "feeling or showing pleasure")],
        blng=[("She was happy to see her old teacher again.", "再次见到老师她很高兴。")],
        phrs=[], rels=[("happiness", "幸福")]),
    "write": dict(star=False, page=18, uk="raɪt", us="raɪt",
        senses=["v. 写，书写"], cstar=5,
        collins=[("VERB", "动词", "写", "Please write your name at the top.", "请在顶部写下你的名字。")],
        en=[("v.", "to make letters or words on paper or a screen")],
        blng=[("He began to write a letter to his family.", "他开始给家人写信。")],
        phrs=[("write down", "记下")], rels=[("writer", "作家")]),
    "light": dict(star=False, page=19, uk="laɪt", us="laɪt",
        senses=["n. 光，光线", "adj. 轻的"], cstar=5,
        collins=[("N-UNCOUNT", "不可数名词", "光", "The room was full of light.", "房间里充满阳光。"),
                 ("ADJ", "形容词", "轻的", "The box is surprisingly light.", "这个箱子出乎意料地轻。")],
        en=[("n.", "energy from the sun or a lamp that lets you see"),
            ("adj.", "not heavy")],
        blng=[("Turn on the light, please.", "请开灯。")],
        phrs=[("in the light of", "鉴于")], rels=[]),
    "time": dict(star=False, page=20, uk="taɪm", us="taɪm",
        senses=["n. 时间；次数"], cstar=5,
        collins=[("N-UNCOUNT", "不可数名词", "时间", "Time passes quickly when you are busy.", "忙碌时时间过得很快。")],
        en=[("n.", "what you measure with a clock")],
        blng=[("We had a great time at the party.", "我们在聚会上玩得很开心。")],
        phrs=[("on time", "准时")], rels=[]),
    "quick": dict(star=True, page=21, uk="kwɪk", us="kwɪk",
        senses=["adj. 快的，迅速的"], cstar=4,
        collins=[("ADJ", "形容词", "迅速的", "He gave a quick answer.", "他迅速给出了回答。")],
        en=[("adj.", "happening or done without delay")],
        blng=[("She took a quick look at the clock.", "她快速看了一眼时钟。")],
        phrs=[], rels=[("quickly", "迅速地")]),
}


def yd_json(w, d):
    """Fabricated youdao-shaped cache record (schema per lib/ydparse.py)."""
    trs = [{"tr": [{"l": {"i": [s]}}]} for s in d["senses"]]
    collins_entries = [{
        "star": d["cstar"],
        "entries": {"entry": [{"tran_entry": [
            {"pos_entry": {"pos": pos, "pos_tips": tip},
             "tran": tran,
             "exam_sents": {"sent": [{"eng_sent": en, "chn_sent": zh}]}}
            for pos, tip, tran, en, zh in d["collins"]]}]},
    }]
    return {
        "ec": {"word": [{"ukphone": d["uk"], "usphone": d["us"],
                         "ukspeech": "", "usspeech": "",
                         "trs": trs}]},
        "collins": {"collins_entries": collins_entries},
        "ee": {"word": {"trs": [{"pos": pos, "tr": [{"l": txt}]} for pos, txt in d["en"]]}},
        "blng_sents_part": {"sentence-pair": [
            {"sentence-eng": en, "sentence-translation": zh} for en, zh in d["blng"]]},
        "phrs": {"phrs": [{"phr": {"headword": head, "trs": [{"tr": zh}]}}
                          for head, zh in d["phrs"]]} if d["phrs"] else {},
        "rel_word": {"rels": [{"rel": {"words": [{"word": w2, "tran": t2}]}}
                              for w2, t2 in d["rels"]]} if d["rels"] else {},
    }


def main():
    os.makedirs(CACHE, exist_ok=True)
    entries, amap = [], {}
    for i, (w, d) in enumerate(DATA.items()):
        json.dump(yd_json(w, d), open(os.path.join(CACHE, w + ".json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        entries.append({"word": w, "display": w, "official": w, "variants": [],
                        "star": d["star"], "page": d["page"], "source": "fetch"})
        amap[w] = {"uk": f"yd_{w}_uk.mp3", "us": f"yd_{w}_us.mp3"}
    json.dump({"entries": entries},
              open(os.path.join(DATA_DIR, "entries_7619.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(amap, open(os.path.join(DATA_DIR, "audio_map2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"generated: {len(entries)} entries, {len(entries)} cache files, audio map {len(amap)}")
    print(f"starred: {sum(1 for e in entries if e['star'])}")


if __name__ == "__main__":
    main()
