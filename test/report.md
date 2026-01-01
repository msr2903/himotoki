# Detailed Evaluation Report: Himotoki vs Ichiran

- **Splitting Similarity:** 2.86%
- **Formatting Similarity:** 2.86%

## Category Performance

| Category | Splitting | Formatting |
| :--- | :--- | :--- |
| particles_and_conjunctions | 0.0% | 0.0% |
| polite_and_casual | 0.0% | 0.0% |
| complex_grammar | 20.0% | 20.0% |
| news_and_technical | 0.0% | 0.0% |
| literature_and_idioms | 0.0% | 0.0% |
| compound_verbs_and_adjectives | 0.0% | 0.0% |
| formatting_test | 0.0% | 0.0% |

## Sentence Splitting Mismatches (Main Point)

### particles_and_conjunctions

**Sentence:** 私は猫が好きですが、犬も好きです。
```
Ichiran:  [私 | は | 猫 | が | 好き | ですが]
Himotoki: [私 | は | 猫 | が | 好き | です | が | 、 | 犬 | も | 好き | です | 。]
```

**Sentence:** 雨が降ったので、家で本を読みました。
```
Ichiran:  [雨が降った | ので]
Himotoki: [雨が降った | の | で | 、 | 家 | で | 本 | を | 読みました | 。]
```

**Sentence:** 明日晴れたら、公園に行きましょう。
```
Ichiran:  [明日 | 晴れたら]
Himotoki: [明日 | 晴れたら | 、 | 公園 | に | 行きましょう | 。]
```

**Sentence:** 銀行へ行ってから、デパートで買い物をします。
```
Ichiran:  [銀行 | へ | 行って | から]
Himotoki: []
```

**Sentence:** 彼が来るかどうか、まだ分かりません。
```
Ichiran:  [彼 | が | 来る | かどうか]
Himotoki: [彼 | が | 来る | か | どう | か | 、 | まだ | 分かりません | 。]
```

### polite_and_casual

**Sentence:** 今日はとても良い天気ですね。
```
Ichiran:  [今日 | は | とても | 良い天気 | です | ね]
Himotoki: [今日 | は | と | て | も | 良い | 天気 | で | すね | 。]
```

**Sentence:** お名前を伺ってもよろしいでしょうか？
```
Ichiran:  [お名前 | を | 伺って | も | よろしいでしょう | か]
Himotoki: []
```

**Sentence:** 最近、どうしてる？元気にしてるかな。
```
Ichiran:  [最近]
Himotoki: []
```

**Sentence:** 失礼ですが、どちら様でしょうか。
```
Ichiran:  [失礼 | ですが]
Himotoki: [失礼 | です | が | 、 | どちら | 様 | で | しょう | か | 。]
```

**Sentence:** あそこに座っている人は誰？」
```
Ichiran:  [あそこ | に | 座って | いる | 人 | は | 誰]
Himotoki: []
```

### complex_grammar

**Sentence:** 勉強しなければならないことは山ほどあります。
```
Ichiran:  [勉強 | しなければ | ならない | こと | は | 山ほど | あります]
Himotoki: [勉強 | しなければ | な | らない | こ | と | は | 山 | ほど | あります | 。]
```

**Sentence:** もっと早く起きればよかったと思っています。
```
Ichiran:  [もっと | 早く | 起きれば | よかった | と | 思って | います]
Himotoki: []
```

**Sentence:** 彼はもうすぐ来るはずですが、まだ来ません。
```
Ichiran:  [彼 | は | もうすぐ | 来る | はずです | が]
Himotoki: [彼 | は | もうす | ぐ | 来る | は | ず | です | が | 、 | まだ | 来ません | 。]
```

**Sentence:** 子供の頃、よくこの川で遊んだものです。
```
Ichiran:  [子供の頃]
Himotoki: [子供の頃 | 、 | よ | く | こ | の | 川 | で | 遊んだ | も | ので | す | 。]
```

### news_and_technical

**Sentence:** 最新の技術を用いて、問題を解決する必要があります。
```
Ichiran:  [最新 | の | 技術 | を | 用いて]
Himotoki: [最新 | の | 技術 | を | 用いて | 、 | 問題 | を | 解決 | する | 必要 | が | あります | 。]
```

**Sentence:** 政府は新しい経済政策を発表することを決定しました。
```
Ichiran:  []
Himotoki: [政府 | は | 新しい | 経済 | 政策 | を | 発 | 表する | こ | と | を | 決定 | しました | 。]
```

**Sentence:** 人工知能の急速な進歩が社会に大きな影響を与えています。
```
Ichiran:  [人工知能 | の | 急速 | な | 進歩 | が | 社会 | に | 大きな | 影響 | を | 与えて | います]
Himotoki: []
```

**Sentence:** 円相場は一時、一ドル百五十円台まで値下がりしました。
```
Ichiran:  []
Himotoki: [円相場 | は | 一時 | 、 | 一ドル | 百 | 五十 | 円 | 台 | まで | 値下がり | しました | 。]
```

**Sentence:** 環境保護のために、私たちは何ができるでしょうか。
```
Ichiran:  []
Himotoki: [環境保護 | の | ため | に | 、 | 私たち | は | 何 | ができる | で | しょう | か | 。]
```

### literature_and_idioms

**Sentence:** 吾輩は猫である。名前はまだ無い。
```
Ichiran:  [吾輩は猫である]
Himotoki: [吾輩 | は | 猫 | で | ある | 。 | 名前 | は | まだ | 無い | 。]
```

**Sentence:** 栴檀は双葉より芳しという言葉があります。
```
Ichiran:  []
Himotoki: [栴檀 | は | 双葉 | より | 芳し | と | いう | 言葉 | が | あります | 。]
```

**Sentence:** 石の上にも三年というように、我慢が大切です。
```
Ichiran:  [石の上にも三年 | という | ように]
Himotoki: [石 | の | 上 | に | も | 三年 | と | いう | よ | う | に | 、 | 我慢 | が | 大切 | です | 。]
```

**Sentence:** 月日は百代の過客にして、行かふ年も又旅人なり。
```
Ichiran:  []
Himotoki: [月日 | は | 百代 | の | 過 | 客 | にして | 、 | 行か | ふ | 年 | も | 又 | 旅 | 人な | り | 。]
```

**Sentence:** 雨ニモマケズ、風ニモマケズ、丈夫ナカラダヲモチ。
```
Ichiran:  [雨 | ニモマケズ]
Himotoki: [雨 | ニ | モ | マ | ケ | ズ | 、 | 風 | ニ | モ | マ | ケ | ズ | 、 | 丈夫 | ナカ | ラ | ダヲ | モチ | 。]
```

### compound_verbs_and_adjectives

**Sentence:** 昨日は一晩中、泣き明かしました。
```
Ichiran:  []
Himotoki: [昨日 | は | 一晩中 | 、 | 泣き | 明かしました | 。]
```

**Sentence:** この問題は、非常に考えさせられる内容です。
```
Ichiran:  [この | 問題 | は]
Himotoki: [こ | の | 問題 | は | 、 | 非常に | 考えさせられる | 内容 | です | 。]
```

**Sentence:** 彼女の歌声は、人々の心を揺さぶり続けています。
```
Ichiran:  [彼女 | の | 歌声 | は]
Himotoki: []
```

**Sentence:** あきらめずに、最後までやり遂げることが重要だ。
```
Ichiran:  [あきらめず | に]
Himotoki: [あきらめ | ず | に | 、 | 最後 | まで | や | り | 遂げる | こ | と | が | 重要 | だ | 。]
```

**Sentence:** 青白く光る星が、夜空に美しく輝いています。
```
Ichiran:  [青白く | 光る | 星 | が]
Himotoki: []
```

### formatting_test

**Sentence:** 2026年1月1日にイベントが開催されます。
```
Ichiran:  []
Himotoki: [2026年 | 1月 | 1日 | に | イベント | が | 開催 | されます | 。]
```

**Sentence:** 東京(とうきょう)は日本の首都です。
```
Ichiran:  [東京]
Himotoki: [東京 | ( | とうきょう | ) | は | 日本 | の | 首都 | です | 。]
```

**Sentence:** URLは https://example.com です。
```
Ichiran:  []
Himotoki: [URL | は |  https://example.com  | です | 。]
```

**Sentence:** 「こんにちは」と彼は言った。
```
Ichiran:  []
Himotoki: [「 | こん | に | ち | は | 」 | と | 彼 | は | 言った | 。]
```

**Sentence:** 1,234円の買い物をしました。
```
Ichiran:  []
Himotoki: [1, | 234円 | の | 買い物 | を | しました | 。]
```


## Metadata/Formatting Mismatches

