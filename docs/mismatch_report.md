# Mismatch Review Report

This report compares tokenization differences and selects which side looks better based on segmentation quality.

| # | Sentence | Category | First diff | Better | Beads? |
|---:|---|---|---|---|---|
| 1 | 君の名前を呼ぶたびに胸が張り裂けそうになる | himotoki_split | I: 張り裂け / そうになる → H: 張り裂けそう / に / なる | Himotoki |  |
| 2 | カラオケでアニソン縛りしようぜって言ったのお前だろ歌えよ | same_count_diff_tokens | I: ぜって / 言 / った → H: ぜ / って / 言った | Himotoki |  |
| 3 | 古の契約に基づき我汝を召喚せん。答えよ英霊たちよ | himotoki_split | I: ∅ → H: 。 / 答え / よ / 英霊 / たち / よ | Himotoki |  |
| 4 | 魔王城の結界を破るには四つの精霊石を集める必要があるんだ | same_count_diff_tokens | I: 魔 / 王城 → H: 魔王 / 城 | Himotoki |  |
| 5 | 詠唱を破棄して魔法を発動させるなんてあいつ化け物か | himotoki_split | I: 発動させる / なんて → H: 発動させるな / ん / て | Ichiran | himotoki-nwd |
| 6 | 教育現場ではタブレット端末を活用したICT教育の導入が加速しています | himotoki_split | I: ∅ → H: ICT / 教育 / の / 導入 / が / 加速しています | Himotoki |  |
| 7 | 国内最大級の音楽フェスティバルが3年ぶりに開催され会場は熱気に包まれました | same_count_diff_tokens | I: 3 / 年ぶり → H: 3年 / ぶり | Himotoki |  |
| 8 | 誰になんと言われようと私は彼のことを信じ続けるわ | himotoki_merge | I: 信じ / 続ける → H: 信じ続ける | Himotoki |  |
| 9 | 救急車の受け入れ要請が来ていますがICUは満床で断るしかありません | himotoki_split | I: ∅ → H: ICU / は / 満床 / で / 断る / しか / ありません | Himotoki |  |
| 10 | この事件裏に大きな組織が関わっている可能性があるな深入りするなよ | same_count_diff_tokens | I: 深入りする / なよ → H: 深入りするな / よ | Himotoki |  |
| 11 | 私は無実だ誰かが私を陥れようとして罠を仕掛けたんだ | same_count_diff_tokens | I: 仕掛けた / ん → H: 仕掛け / たん | Himotoki |  |
| 12 | 警察内部に情報を漏らしているスパイがいる誰も信用するな | himotoki_merge | I: 信用する / な → H: 信用するな | Himotoki |  |
| 13 | すみません写真を撮っていただけますか背景のタワーも入れてほしいんですけど | himotoki_split | I: 写真を撮っていただけます → H: 写真を撮って / いただけます | Himotoki |  |
| 14 | ポイントカードをお持ちでない場合はこちらのアプリがお得ですよ | himotoki_merge | I: で / ない → H: でない | Himotoki |  |
| 15 | お支払いは現金のみとなっておりますがよろしいでしょうか | himotoki_split | I: となって → H: と / なって | Himotoki |  |
| 16 | ただいまセール期間中でして2点以上お買い上げでさらに10%オフになります | himotoki_split | I: ∅ → H: 10% / オフ / に / なります | Himotoki |  |
| 17 | 早速のご返信誠にありがとうございます。内容を拝見いたしました | himotoki_split | I: ∅ → H: 。 / 内容 / を / 拝見いたしました | Himotoki |  |
| 18 | リスクヘッジの観点から代替案も用意しておくべきではないでしょうか | same_count_diff_tokens | I: 代替 / 案 → H: 代替案 | Himotoki |  |
| 19 | 貴重なご指摘をいただきありがとうございます。社内で共有させていただきます | himotoki_split | I: ∅ → H: 。 / 社内 / で / 共有させていただきます | Himotoki |  |
| 20 | 失礼ですがお名前をもう一度お伺いしてもよろしいでしょうか | himotoki_merge | I: 失礼 / ですが → H: 失礼ですが | Himotoki |  |
| 21 | 飯食い行こうぜ腹減って死にそうなんだわ | himotoki_merge | I: な / ん / だ → H: なんだ | Himotoki |  |
| 22 | めんどくせーな明日やればいいだろ今日はもう寝る | same_count_diff_tokens | I: めんどく / せー → H: めんど / くせー | Himotoki |  |
| 23 | 別に怒ってねーしただ疲れてるだけだって言ってんだろ | same_count_diff_tokens | I: し / ただ → H: した / だ | Ichiran | himotoki-f5d |
| 24 | そろそろ行らなきゃ遅刻しちゃうよ（行かなければ） | himotoki_split | I: ∅ → H: （ / 行かなければ / ） | Himotoki |  |
| 25 | これ食べちゃっていい（食べてしまって） | himotoki_split | I: ∅ → H: （ / 食べてしまって / ） | Himotoki |  |
| 26 | 宿題やっといた方がいいよ（やっておいた） | himotoki_split | I: ∅ → H: （ / やっておいた / ） | Himotoki |  |
| 27 | 明日までに終わらせなきゃなんないんだ（終わらせなければならない） | himotoki_split | I: ∅ → H: （ / 終わらせなければ / ならない / ） | Himotoki |  |
| 28 | そんなこと言ったって無理なもんは無理だよ（言ってもものは） | himotoki_split | I: ∅ → H: （ / 言っても / もの / は / ） | Himotoki |  |
| 29 | 早く準備しなよみんな待ってるんだから（しなさいよ） | himotoki_split | I: ∅ → H: （ / しなさい / よ / ） | Himotoki |  |
| 30 | これ買っとくね後で半分払ってくれればいいから（買っておく） | himotoki_split | I: ∅ → H: （ / 買っておく / ） | Himotoki |  |
| 31 | 雨降りそうだから傘持ってった方がいいかもよ | same_count_diff_tokens | I: 雨降り / そう → H: 雨 / 降りそう | Himotoki |  |
| 32 | そんなに焦んなくても大丈夫だよまだ時間あるし（焦らなくても） | himotoki_split | I: ∅ → H: （ / 焦らなくても / ） | Himotoki |  |
| 33 | これ読んどいてねテストに出るかもしれないから（読んでおいて） | himotoki_split | I: ∅ → H: （ / 読んでおいて / ） | Himotoki |  |
| 34 | 食べ放題なんだから元取れるまで食べまくろうぜ | himotoki_merge | I: な / ん → H: なん | Himotoki |  |
| 35 | 寝よっかな明日早いし（寝ようかな） | himotoki_split | I: ∅ → H: （ / 寝よう / かな / ） | Himotoki |  |
| 36 | どんなに困難な状況であっても希望を捨てずに努力し続けることこそが重要だ | himotoki_merge | I: 努力し / 続ける → H: 努力し続ける | Himotoki |  |
| 37 | 明日までにレポートを提出させられるなんてもっと早く言ってくれればよかったのに | himotoki_split | I: 提出させられる / なんて → H: 提出させられるな / ん / て | Ichiran | himotoki-5zp |
| 38 | 万が一失敗した時のためにプランBを用意しておくべきだ | himotoki_split | I: ∅ → H: B / を / 用意しておく / べき / だ | Himotoki |  |
