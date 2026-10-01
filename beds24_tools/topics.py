"""ゲストメッセージを施設情報シートの列（質問項目）に振り分けるためのキーワード辞書。

1つのメッセージが複数の項目に当たることがある（あくまで一次仕分け。最終判断は人が読む）。
columns が空の項目はシートに列が無い質問（新しい列・FAQ の候補）。
パターンは正規表現で、大文字小文字は区別しない。
"""
import re

TOPICS = [
    ("鍵・入室方法", ["鍵"], [
        r"\bkeys?\b", r"door ?code", r"pass ?code", r"\bpin\b", r"\block", r"key ?pad", r"key ?box",
        r"unlock", r"can.?t (get|go) in", r"(enter|get into) the (room|building|apartment)",
        "鍵", "カギ", "キーボックス", "キーコード", "暗証番号", "パスコード", "オートロック", "解錠", "開かない", "入れない",
        "钥匙", "门锁", "开门", "进不去", "门禁", "열쇠", "도어락", "문이 안", "들어갈 수"]),
    ("チェックイン方法・案内", ["チェックインガイド", "説明書"], [
        r"how (do|can|to) (we |i )?check.?in", r"check.?in (instructions?|guide|process|procedure|details|info)",
        r"self.?check.?in", r"house ?(manual|guide|rules)", r"instructions",
        "チェックイン方法", "チェックインの方法", "チェックインの手順", "チェックイン案内", "ハウスマニュアル", "説明書",
        "入住指南", "怎么入住", "如何入住", "入住流程", "체크인 방법", "체크인 안내"]),
    ("住所・行き方・最寄り駅", ["住所", "Map", "最寄り駅", "アクセス"], [
        r"address", r"location", r"directions?", r"how (do|can) (we |i )?get (to|there)", r"how to get",
        r"(nearest|closest) station", r"station", r"\bexit\b", r"google ?maps?", r"\bmap\b", r"subway", r"metro",
        "住所", "場所", "行き方", "道順", "最寄", "駅", "出口", "迷", "地址", "位置", "怎么走", "车站", "地铁", "出口",
        "주소", "위치", "가는 방법", "지하철", "출구"]),
    ("階数・エレベーター", ["階層"], [
        r"\bfloor\b", r"elevator", r"\blift\b", r"stairs",
        "階段", "エレベーター", "エレベータ", "何階", "电梯", "楼梯", "几楼", "엘리베이터", "계단", "몇 층"]),
    ("寝具・ベッド", ["寝具"], [
        r"\bbeds?\b", r"sofa ?bed", r"futon", r"mattress", r"pillows?", r"blankets?", r"duvet",
        "ベッド", "布団", "枕", "毛布", "掛け布団", "沙发床", "被子", "枕头", "床铺", "침대", "소파베드", "이불", "베개"]),
    ("駐車場", ["駐車場"], [
        r"parking", r"park (the|my|our|a) car", r"car ?park", r"garage",
        "駐車", "パーキング", "停车", "车位", "주차"]),
    ("設備（有無）", ["設備"], [
        r"kitchen", r"microwave", r"\boven\b", r"stove", r"cooktop", r"rice cooker", r"kettle", r"fridge",
        r"refrigerator", r"freezer", r"washing machine", r"\bwasher\b", r"dryer", r"\biron\b", r"hair ?dryer",
        r"\btv\b", r"television", r"netflix", r"vacuum", r"dishes", r"cutlery", r"utensils", r"\bpots?\b",
        r"\bpans?\b", r"knife", r"hangers?", r"crib", r"high ?chair",
        "キッチン", "電子レンジ", "レンジ", "コンロ", "炊飯器", "ケトル", "冷蔵庫", "洗濯機", "乾燥機", "アイロン",
        "ドライヤー", "テレビ", "掃除機", "食器", "鍋", "フライパン", "包丁", "ハンガー",
        "厨房", "微波炉", "冰箱", "洗衣机", "烘干", "吹风机", "电视", "熨斗", "锅", "餐具",
        "주방", "전자레인지", "냉장고", "세탁기", "건조기", "드라이기", "다리미", "텔레비전", "식기"]),
    ("アメニティ", ["アメニティ"], [
        r"amenit", r"tooth ?brush", r"tooth ?paste", r"shampoo", r"conditioner", r"body ?(soap|wash)", r"\bsoap\b",
        r"towels?", r"slippers?", r"razor", r"\bcomb\b", r"cotton swab",
        "歯ブラシ", "歯磨き", "シャンプー", "リンス", "コンディショナー", "ボディソープ", "ボディーソープ", "石鹸", "石けん",
        "スリッパ", "タオル", "アメニティ", "カミソリ",
        "牙刷", "牙膏", "洗发", "沐浴", "拖鞋", "毛巾", "칫솔", "치약", "샴푸", "바디워시", "슬리퍼", "수건", "어메니티"]),
    ("チェックイン時刻", ["チェックイン"], [
        r"check.?in time", r"what time.{0,20}check.?in", r"check.?in (is |starts )?(at|from)",
        r"チェックイン(時間|時刻|は何時)", "何時からチェックイン", "入住时间", "几点入住", "几点可以入住", "체크인 시간", "몇 시.{0,6}체크인"]),
    ("チェックアウト時刻・手続き", ["チェックアウト"], [
        r"check.?out time", r"what time.{0,20}check.?out", r"check.?out (is |at |by )",
        r"check.?out (instructions?|procedure|process)", r"how (do|to) (we |i )?check.?out", r"where (should|do) (we|i) leave the key",
        r"チェックアウト(時間|時刻|は何時|の方法|方法|の手順)", "退房时间", "几点退房", "如何退房", "退房流程", "체크아웃 시간", "체크아웃 방법"]),
    ("人数・追加料金", ["定員", "基本", "追加"], [
        r"how many (people|guests|persons)", r"extra (person|guest|people|bed)", r"additional (person|guest|people|fee|charge)",
        r"max(imum)? (occupancy|guests|people|capacity)", r"add (a |one |another )?(guest|person|adult|child)",
        r"more (people|guests)", r"number of guests", r"(one|1|two|2) more (person|people|guest)",
        "定員", "人数", "追加料金", "人追加", "何名", "何人", "入住人数", "加人", "增加人数", "多一个人", "인원", "추가 요금"]),
    ("荷物預け（IN前・OUT後）", ["荷物預チェックイン前", "荷物預チェックアウト後"], [
        r"luggage", r"baggage", r"\bbags?\b", r"suitcases?", r"store (our|my) ", r"drop (off )?(our|my) ",
        "荷物", "預け", "預かり", "スーツケース", "キャリー", "行李", "寄存", "짐", "캐리어", "보관"]),
    ("コインロッカー", ["コインロッカー"], [
        r"lockers?", "コインロッカー", "ロッカー", "储物柜", "寄存柜", "사물함", "코인로커"]),
    ("深夜到着", ["深夜チェックイン"], [
        r"late (arrival|check.?in)", r"arriv\w* (very |quite )?late", r"late at night", r"midnight",
        r"after (10|11|22|23) ?(pm|:00|o.?clock)?", r"flight (is |was |got )?delayed", r"\bdelay",
        "深夜", "夜遅", "遅い時間", "遅くなり", "遅れ", "到着が遅", "0時", "24時", "遅延",
        "晚到", "半夜", "很晚", "凌晨", "延误", "늦게", "늦은 시간", "자정", "지연"]),
    ("アーリーチェックイン", ["アーリーチェックイン"], [
        r"early check.?in", r"check.?in (early|earlier)", r"arriv\w* early", r"earlier than",
        "アーリー", "早め", "早く着", "早く到着", "早い時間", "提前入住", "提早入住", "早点入住", "提前到",
        "얼리 체크인", "일찍", "조기 체크인"]),
    ("レイトチェックアウト", ["レイトチェックアウト"], [
        r"late check.?out", r"check.?out (late|later)", r"stay (a bit |a little )?longer",
        "レイト", "遅め", "チェックアウトを遅", "延迟退房", "晚点退房", "推迟退房", "레이트 체크아웃", "늦은 체크아웃", "늦게 체크아웃"]),
    ("ゴミ捨て", ["ゴミ捨て方"], [
        r"trash", r"garbage", r"rubbish", r"\bwaste\b", r"\bbins?\b", r"recycl",
        "ゴミ", "ごみ", "分別", "垃圾", "쓰레기", "분리수거"]),
    ("粗大ごみ（スーツケース処分等）", ["粗大ごみ"], [
        r"(dispose|throw away|get rid) (of )?(a |an |our |my |the )?(old |broken )?(suitcase|luggage)",
        r"leave (a |the |our |my )?(old |broken )?suitcase",
        "粗大", r"スーツケース.{0,10}(捨て|処分)", r"(捨て|処分).{0,10}スーツケース",
        r"扔.{0,6}行李箱", r"行李箱.{0,6}扔", r"캐리어.{0,6}버리"]),
    ("Wi-Fi", ["Wi-Fi"], [
        r"wi-?fi", r"wireless", r"internet", r"\bssid\b", r"password", r"router",
        "ワイファイ", "ネット", "パスワード", "無線", "无线", "网络", "와이파이", "인터넷"]),
    ("空港アクセス", ["空港アクセス"], [
        r"airport", r"haneda", r"narita", r"\bhnd\b", r"\bnrt\b", r"skyliner", r"limousine",
        "空港", "羽田", "成田", "スカイライナー", "リムジン", "机场", "공항", "하네다", "나리타"]),
    ("スーパー・コンビニ", ["スーバー/コンビニ"], [
        r"supermarket", r"grocer", r"convenience store", r"konbini", r"7-?eleven", r"seven.?eleven",
        r"family ?mart", r"lawson",
        "スーパー", "コンビニ", "セブン", "ファミマ", "ローソン", "超市", "便利店", "마트", "편의점"]),
    ("レストラン・飲食", ["レストラン"], [
        r"restaurant", r"where (can|to|should) (we |i )?eat", r"\bfood\b", r"dinner", r"lunch", r"breakfast",
        r"ramen", r"sushi", r"izakaya", r"\bcafe", r"recommend",
        "レストラン", "飲食", "ご飯", "ランチ", "ディナー", "朝食", "食事", "おすすめ", "オススメ", "居酒屋", "ラーメン",
        "寿司", "カフェ", "餐厅", "饭店", "吃饭", "美食", "推荐", "早餐", "식당", "맛집", "레스토랑", "추천"]),
    ("温泉・銭湯", ["温泉/銭湯"], [
        r"onsen", r"sento", r"hot spring", r"public bath", r"bath ?house",
        "温泉", "銭湯", "泡汤", "澡堂", "온천", "목욕탕", "대중탕"]),
    ("コインランドリー", ["コインランドリー"], [
        r"laundromat", r"coin laundry", r"laundry",
        "コインランドリー", "ランドリー", "自助洗衣", "洗衣店", "빨래방", "코인세탁"]),
    ("薬局・病院", ["薬局/病院"], [
        r"pharmacy", r"drug ?store", r"hospital", r"clinic", r"doctor", r"medicine", r"medical", r"fever", r"first aid",
        "薬局", "ドラッグストア", "薬", "病院", "クリニック", "医者", "熱が",
        "药店", "药", "医院", "诊所", "看病", "약국", "병원"]),
    ("観光", ["観光地"], [
        r"sightseeing", r"tourist", r"attractions?", r"places to (visit|go|see)", r"things to do",
        r"asakusa", r"skytree", r"ueno", r"akihabara", r"shibuya", r"shinjuku", r"disney",
        "観光", "名所", "見どころ", "浅草", "スカイツリー", "上野", "秋葉原", "景点", "旅游", "游玩", "관광", "명소", "가볼"]),
    ("タオル・リネン交換", ["タオル・リネン交換"], [
        r"(new|more|extra|clean|fresh|additional) towels?", r"(change|replace) (the )?(towels|sheets|linens?|bedding)",
        r"linens?", r"\bsheets\b",
        r"タオル.{0,10}(交換|追加|替え|足り|もう)", r"(交換|追加).{0,6}タオル", "シーツ", "リネン",
        "换毛巾", r"毛巾.{0,6}(换|更换|不够|多)", "床单", r"수건.{0,6}(교체|추가|더)", "시트"]),
    ("清掃・汚れ・衛生", ["清掃"], [
        r"clean(ing)? (the )?(room|apartment|place)", r"housekeeping", r"\bmaid\b", r"dirty", r"not clean",
        r"\bhairs?\b", r"\bdust", r"\bsmell", r"\bbugs?\b", r"insects?", r"cockroach", r"mold|mould",
        "清掃", "掃除", "汚", "髪の毛", "ホコリ", "埃", "虫", "ゴキブリ", "臭", "におい", "匂い", "カビ",
        "打扫", "清洁", "脏", "头发", "蟑螂", "味道", "霉", "청소", "더러", "벌레", "냄새", "곰팡이"]),
    ("喫煙", ["喫煙"], [
        r"smok", r"cigarette", r"\bvape", r"e-?cig", r"iqos",
        "喫煙", "タバコ", "たばこ", "煙草", "禁煙", "吸烟", "抽烟", "香烟", "흡연", "담배"]),
    ("設備の使い方・故障", ["設備使用方法"], [
        r"how (do|to|can) (i |we )?(use|turn on|turn off|operate|switch|work)", r"not working", r"(doesn|don|won|isn).?t (work|turn)",
        r"does not work", r"broken", r"remote", r"air ?con", r"\ba/?c\b", r"heater", r"heating", r"thermostat",
        r"\berror\b", r"clogged", r"blocked", r"flush",
        "使い方", "使用方法", "動かない", "使えない", "つかない", "点かない", "壊れ", "故障", "エラー", "リモコン",
        "エアコン", "暖房", "冷房", "詰まり", "流れない",
        "怎么用", "如何使用", "坏了", "不能用", "没反应", "遥控", "空调", "暖气", "堵",
        "사용법", "고장", "작동", "리모컨", "에어컨", "난방", "막혔"]),
    ("ブレーカー・停電", ["ブレーカー"], [
        r"power (is )?(out|off|cut|outage)", r"no (power|electricity)", r"blackout", r"breaker", r"\bfuse", r"tripped",
        "ブレーカー", "停電", r"電気が(つかない|消え|落ち|使えない)", "跳闸", "停电", "断电", "没电", "정전", "차단기"]),
    ("お湯・ガス", ["ガスメーター"], [
        r"hot water", r"\bgas\b", r"water (is )?(cold|not hot)", r"cold (water|shower)",
        "ガス", "お湯", "湯が出", "ガスメーター", "热水", "煤气", "燃气", "온수", "가스", "뜨거운 물"]),
    ("薪ストーブ", ["薪ストーブ"], [r"wood ?stove", r"fire ?place", "薪ストーブ", "暖炉", "壁炉", "벽난로"]),
    ("焚き火", ["焚き火"], [r"bon ?fire", r"camp ?fire", r"fire ?pit", "焚き火", "篝火", "모닥불"]),
    ("BBQ", ["BBQ"], [r"\bbbq\b", r"barbecue", r"barbeque", r"\bgrill", "バーベキュー", "BBQ", "烧烤", "바베큐"]),
    ("サウナ", ["サウナ"], [r"sauna", "サウナ", "桑拿", "사우나"]),
    ("花火・プール", ["花火,プール"], [r"firework", r"\bpool\b", r"swim", "花火", "プール", "烟花", "泳池", "불꽃", "수영장"]),
    ("トイレ・浴室", ["トイレ/バスルームの数"], [
        r"toilet", r"bathroom", r"bath ?tub", r"shower", r"restroom", r"washroom",
        "トイレ", "バスルーム", "浴室", "風呂", "シャワー", "バスタブ", "湯船",
        "厕所", "卫生间", "浴缸", "淋浴", "화장실", "욕실", "욕조", "샤워"]),
    ("広さ", ["m2"], [
        r"square (meters?|metres?|feet)", r"\bsqm\b", r"\bm2\b", "㎡", r"how big", r"size of the (room|apartment)",
        "広さ", "平米", "面积", "平方", "크기", "평수"]),
    ("緊急連絡・電話", ["緊急連絡先"], [
        r"emergency", r"phone (number)?", r"call (you|someone|the host)", r"contact (number|you|someone)", r"urgent",
        "緊急", "電話", "連絡先", "至急", "紧急", "电话", "联系方式", "긴급", "전화", "연락처"]),
    ("備品切れ・補充", ["備品補充対応"], [
        r"run out", r"ran out", r"out of (toilet paper|tissue|shampoo|soap|detergent)", r"toilet paper", r"tissues?",
        r"refill", r"replenish", r"need more", r"missing",
        "足りない", "切れ", "なくなり", "無くなり", "補充", "トイレットペーパー", "ティッシュ",
        "用完", "没有了", "补充", "卫生纸", "纸巾", "부족", "떨어졌", "보충", "휴지"]),
    ("タクシー", ["タクシー"], [r"taxi", r"\buber\b", r"\bcab\b", "タクシー", "出租车", "打车", "的士", "택시"]),
    ("レストラン予約代行", ["レストラン予約代行"], [
        r"(make|book) (a )?reservation", r"book (a table|for us)", r"reserve (a )?(table|restaurant)",
        r"could you (book|reserve)", r"レストラン.{0,10}予約", r"予約.{0,6}(代行|して(もらえ|いただけ))",
        "代订", r"帮.{0,4}(预订|订)", r"대신.{0,4}예약", r"예약.{0,4}대신"]),
    ("車椅子・バリアフリー", ["車椅子"], [
        r"wheel ?chair", r"accessib", r"mobility", "車椅子", "車いす", "バリアフリー", "轮椅", "无障碍", "휠체어", "배리어프리"]),
    ("未成年のみの宿泊", ["未成年のみの宿泊"], [
        r"\bminors?\b", r"under 18", r"under ?age", r"under the age", r"teenagers?",
        "未成年", "18歳未満", "未成年人", "미성년"]),
    ("宿泊者以外の入室・来客", ["宿泊者以外の入室"], [
        r"visitors?", r"friends? (to )?(come|visit|over|stop by|drop by)", r"bring (a )?friend", r"come over",
        r"not staying",
        "友人", "友達", "訪問", "来客", "遊びに", "访客", r"朋友.{0,6}(来|过来|拜访)", "방문객", "친구"]),
    ("ペット", ["ペット"], [
        r"\bpets?\b", r"\bdogs?\b", r"\bcats?\b", r"service animal",
        "ペット", "犬", "猫", "宠物", "狗", "반려동물", "애완", "강아지", "고양이"]),
    ("パーティー", ["パーティー"], [
        r"part(y|ies)", r"celebrat", r"birthday", r"gathering",
        "パーティー", "パーティ", "誕生日", "宴会", "派对", "聚会", "生日", "파티", "생일"]),
    ("鍵の紛失", ["鍵の紛失"], [
        r"lost (the |my |our )?keys?", r"lose (the )?keys?", r"keys? (is |are )?(lost|missing)",
        r"鍵.{0,6}(なくし|無くし|紛失|失くし)", r"钥匙.{0,4}(丢|不见)", r"열쇠.{0,6}(잃어|분실)"]),
    ("キャンセル・返金・予約変更", ["ゲスト都合キャンセル希望（返金希望）"], [
        r"cancel", r"refund", r"money back", r"change (the |my |our )?(dates?|reservation|booking)", r"modif",
        "キャンセル", "返金", "払い戻", "日程変更", "予約変更", "取消", "退款", "退钱", "改日期", "취소", "환불", "변경"]),
    ("不幸・病気による返金", ["不幸時返金（亡くなった、病気等）"], [
        r"passed away", r"\bdied\b", r"death", r"funeral", r"hospitali[sz]ed", r"illness", r"\bsick\b", r"covid", r"injur",
        r"family emergency",
        "亡くな", "逝去", "葬儀", "病気", "入院", "体調", "怪我", "コロナ",
        "去世", "葬礼", "生病", "住院", "受伤", "돌아가", "장례", "아파", "입원"]),
    ("自然災害", ["自然災害返金"], [
        r"typhoon", r"earthquake", r"natural disaster", r"\bstorm", r"heavy (snow|rain)", r"flood", r"tsunami",
        r"flight (was |is |got )?cancel",
        "台風", "地震", "災害", "大雪", "大雨", "洪水", "欠航", "台风", "暴雨", "航班取消", "태풍", "지진", "폭설", "결항"]),
    ("忘れ物", ["忘れ物対応"], [
        r"forgot", r"left (my|our|a|an|the) .{0,40}(in|at) the (room|apartment|unit)", r"left behind", r"lost (my|our)",
        r"lost item", r"did you find", r"belongings",
        "忘れ物", "忘れ", "落とし物", "置き忘れ", "忘了", "落下", "遗落", "丢了", "분실", "두고", "잃어버"]),
    ("延泊", ["延泊時の対応"], [
        r"extend", r"extension", r"(extra|another|one more|additional) night", r"stay (one |an |a few )?(more|longer|extra)",
        "延泊", "延長", "もう一泊", "追加で泊", "续住", "延住", "多住", "再住", "연장", "하루 더", "연박"]),
    ("割引・料金", ["割引"], [
        r"discount", r"cheaper", r"(lower|better|special) (the )?price", r"\bdeal\b", r"coupon", r"\bprice\b",
        r"how much", r"\bcost",
        "割引", "値引", "安く", "ディスカウント", "料金", "価格", "値段", "いくら",
        "折扣", "优惠", "便宜", "价格", "多少钱", "할인", "가격", "얼마"]),
    ("汚損（お漏らし・嘔吐等）", ["お漏らし、嘔吐"], [
        r"vomit", r"threw up", r"throw up", r"\bpuke", r"wet the bed", r"bed.?wetting", r"\burin", r"\bpee\b",
        r"\bstains?\b", r"spill",
        "嘔吐", "吐い", "おねしょ", "漏らし", "おもらし", "汚して", "シミ", "こぼし",
        "呕吐", "吐了", "尿床", "弄脏", "洒了", "토했", "구토", "오줌", "얼룩", "쏟"]),
    ("破損（グラス等）", ["グラス破損"], [
        r"\bbroke\b", r"i broke", r"we broke", r"cracked", r"shatter", r"damaged?",
        "割れ", "割って", "割っ", "壊し", "破損", "欠け", "打碎", "碎了", "摔坏", "损坏", "깨졌", "깨뜨", "파손"]),
    ("荷物の事前受取・配送", ["荷物事前受取"], [
        r"packages?", r"parcels?", r"deliver", r"amazon", r"\bmail\b", r"shipping", r"ship (to|it|them)", r"post office",
        "宅配", "配達", "荷物を送", "郵送", "アマゾン", "届け", "受け取", "快递", "包裹", "寄到", "收件", "택배", "배송", "소포"]),
    ("宿泊税", ["宿泊税"], [
        r"accommodation tax", r"city tax", r"tourist tax", r"hotel tax", r"lodging tax", r"\btax",
        "宿泊税", "税", "住宿税", "城市税", "숙박세", "세금"]),
    ("乳幼児・添い寝", ["添い寝"], [
        r"infants?", r"\bbab(y|ies)\b", r"toddler", r"\bcribs?\b", r"\bcots?\b", r"co-?sleep",
        r"(child|children|kids?) (under|aged)", r"\d+ ?(years?|yrs?|months?) old",
        "添い寝", "乳児", "幼児", "赤ちゃん", "ベビー", "子ども", "子供", "歳",
        "婴儿", "宝宝", "小孩", "儿童", "婴儿床", "아기", "유아", "어린이"]),
    # ---- ここから下はシートに列が無い質問（新しい列・FAQ の候補） ----
    ("支払い・領収書", [], [
        r"receipt", r"invoice", r"payment", r"\bpay\b", r"credit card", r"\bcash\b",
        "領収書", "請求書", "支払", "インボイス", "決済", "收据", "发票", "付款", "支付", "영수증", "결제"]),
    ("本人確認・パスポート・宿泊者名簿", [], [
        r"passport", r"\bid (card|photo|verification)", r"identity", r"registration", r"guest (info|registration)",
        r"check.?in form", r"\bform\b",
        "パスポート", "本人確認", "身分証", "名簿", "フォーム", "护照", "身份证", "登记", "여권", "신분증"]),
    ("騒音・近隣トラブル", [], [
        r"\bnois[ey]", r"\bloud\b", r"neighbou?r", r"complain",
        "騒音", "うるさ", "騒が", "苦情", "近所", "噪音", "吵", "邻居", "소음", "시끄", "이웃"]),
]

# シートの版によって列名が違うときの別名（例: 旧版の施設早見表では「割引」が「値引き対応」）
COLUMN_ALIASES = {
    "スーバー/コンビニ": ["スーパー/コンビニ", "周辺情報"],
    "レストラン": ["周辺情報"],
    "温泉/銭湯": ["周辺情報"],
    "コインランドリー": ["周辺情報"],
    "薬局/病院": ["周辺情報"],
    "コインロッカー": ["ロッカー"],
    "ゴミ捨て方": ["短期ゴミ", "長期ゴミ"],
    "清掃": ["長期滞在清掃"],
    "設備使用方法": ["リモコン"],
    "割引": ["値引き対応"],
    "お漏らし、嘔吐": ["お漏らし"],
    "不幸時返金（亡くなった、病気等）": ["不幸時返金"],
    "花火,プール": ["花火", "プール"],
}

_COMPILED = [(label, cols, [re.compile(p, re.IGNORECASE) for p in pats]) for label, cols, pats in TOPICS]


def resolve_columns(columns, header):
    """項目の列名を、手元のシートに実際にある列名に読み替える（無ければ別名を探す）。"""
    resolved = []
    for col in columns:
        for name in [col] + COLUMN_ALIASES.get(col, []):
            if name in header and name not in resolved:
                resolved.append(name)
                if name == col:
                    break
    return resolved


def classify(text):
    """テキストに当てはまる項目ラベルのリストを TOPICS の順で返す。"""
    text = text or ""
    return [label for label, _cols, pats in _COMPILED if any(p.search(text) for p in pats)]


def columns_for(label):
    for lab, cols, _pats in TOPICS:
        if lab == label:
            return cols
    return []
