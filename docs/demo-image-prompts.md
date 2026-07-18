# ClaimCraft 演示素材生图 Prompt 集（35 张）

> 适用对象：Stable Diffusion XL / SD3 / Midjourney v6 / DALL·E 3 / Seedream 等主流文生图模型
> 用途：为 ClaimCraft Demo 准备 6 套维权场景所需的全部图片素材
> 生成策略：所有 prompt 遵循 **"截图真实感"** 风格（旗舰手机截图 + 真实 App UI），让观众一眼就能识别为"这是真实纠纷证据"

---

## 一、截图类统一风格规范

### 视觉基调
- **主体**：iPhone 15pro，屏幕内容为真实 App 截图
- **比例**：`9:16`（portrait_4_3 / portrait_16_9），分辨率2556×1179像素
- **光线**：平面均匀打光，无强反光，便于文字识别
- **景深**：全屏清晰，无虚化
- **色调**：高保真屏幕色彩，不做胶片颗粒或滤镜
- **文字**：所有界面文字均为**简体中文**，UI 元素符合中国主流 App 设计语言

### 通用必带元素
- 顶部状态栏：时间 `9:41` / 信号满格 / WiFi / 电量 100%
- 底部小白条

### 通用负面 Prompt（Negative Prompt）
```
lowres, blurry, jpeg artifacts, watermark, signature, username overlay,
distorted text, gibberish characters, broken UI, extra fingers, mutated hands,
3d render, illustration, cartoon, anime, oil painting, watercolor,
oversaturated, hdr, dark background, text errors, double screen
```

---

## 二、6 套场景完整 Prompt 列表

---

### 场景 1 ｜ 网购食品过期 —— 「食安法 148 条 · 十倍赔偿」

#### 📷 E1-1 ｜ 诚品优选客服聊天截图 1
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 对方名称：「诚品优选客服」
  - 时间戳：`2026-01-26 14:32`
  - 买家消息：「我买的饼干过期了，生产日期 2025 年 9 月」
  - 客服回复：「亲，非常抱歉给您带来困扰，已拆封食品暂不支持退货哦」
  - 买家追问：「那十倍赔偿呢？」客服：「已为您申请 5 元平台积分补偿」
  - 买家消息：「我有照片为证！要求按食品安全法 148 条十倍赔偿 1380 元」
  - 客服回复：「亲，请提供生产日期清晰照片 + 购买凭证，我帮您升级处理」

**主 Prompt（英文 · 推荐）**：
```
A realistic modern flagship smartphone screenshot displayed on a black phone bezel with pill notch, showing a Chinese e-commerce customer service chat interface (ChengPin (诚品优选) app). The conversation is between a buyer and "诚品优选客服" at 14:32 on 2026-01-26. The buyer's avatar is on the right with grey bubble saying "我买的饼干过期了，生产日期 2025 年 9 月". The customer service avatar on the left has a white bubble replying "亲，非常抱歉给您带来困扰，已拆封食品暂不支持退货哦". Below, the buyer asks "那十倍赔偿呢？" and the service replies "已为您申请 5 元平台积分补偿". Top status bar shows 9:41, full signal, WiFi, 100% battery. The app uses ChengPin (诚品优选)'s signature red theme (品牌主红). Clean flat UI, high resolution, no blur, photorealistic, 1080x1920.
```

**中文 Prompt（备用）**：

```
一张真实感强的 modern flagship smartphone 截图（黑色边框+居中挖孔），展示诚品优选 App 客服聊天界面。时间戳 2026-01-26 14:32。买家头像在右、气泡为灰底："我买的饼干过期了，生产日期 2025 年 9 月"。客服"诚品优选客服"头像在左、白色气泡回复："亲，非常抱歉给您带来困扰，已拆封食品暂不支持退货哦"。下方买家追问："那十倍赔偿呢？"，客服回复："已为您申请 5 元平台积分补偿"。买家右气泡："我有照片为证！要求按食品安全法 148 条十倍赔偿 1380 元"。客服"诚品优选客服"左气泡："亲，请提供生产日期清晰照片 + 购买凭证，我帮您升级处理"。诚品优选品牌主色调 品牌主红。状态栏 9:41、信号满格、WiFi、电量 100%。1080x1920。
```

---

#### ~~📷 E1-2 ｜ 诚品优选客服聊天截图 2（要求十倍赔偿）~~
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 时间戳：`2026-01-26 15:08`
  - 买家消息：「我有照片为证！要求按食品安全法 148 条十倍赔偿 1380 元」
  - 客服回复：「亲，请提供生产日期清晰照片 + 购买凭证，我帮您升级处理」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot showing 诚品优选 B2C (ChengPin) Chinese e-commerce customer service chat. Time stamp 2026-01-26 15:08. The buyer's message on the right says "我有照片为证！要求按食品安全法 148 条十倍赔偿 1380 元". The "诚品优选客服" replies on the left "亲，请提供生产日期清晰照片 + 购买凭证，我帮您升级处理". ChengPin red theme, top status bar 9:41, full signal, 100% battery. Clean modern Chinese app UI, no blur, 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，诚品优选 App 客服聊天。时间 2026-01-26 15:08。买家右气泡："我有照片为证！要求按食品安全法 148 条十倍赔偿 1380 元"。客服"诚品优选客服"左气泡："亲，请提供生产日期清晰照片 + 购买凭证，我帮您升级处理"。品牌主红，状态栏 9:41，1080x1920。
```

---

#### 📷 E1-3 ｜ 诚品优选订单详情页
- **证据类型**：`product_order`
- **必带文字**：
  - 订单号：`CP202601200088`
  - 下单时间：`2026-01-20 10:14`
  - 商品名：「XX 进口黄油曲奇 480g × 2 盒」
  - 金额：`¥138.00`
  - 状态：「已完成」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 诚品优选 B2C (ChengPin) order detail page in Chinese. Order number "CP202601200088", order time "2026-01-20 10:14", product name "XX 进口黄油曲奇 480g × 2 盒", amount "¥138.00" in large red font, status "已完成" with green check icon. ChengPin red theme, top status bar 9:41, full signal, 100% battery. White card with product image (a box of cookies) and product specs. Clean Chinese e-commerce UI, no blur, 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，诚品优选订单详情页。订单号 CP202601200088，下单时间 2026-01-20 10:14，商品名"XX 进口黄油曲奇 480g × 2 盒"，金额"¥138.00"（红色大字），状态"已完成"（绿色对勾）。品牌主红，状态栏 9:41，1080x1920。
```

---

#### 📷 E1-4 ｜ 私信通支付凭证
- **证据类型**：`payment_record`
- **必带文字**：
  - 收款方：「诚品优选商城」
  - 金额：`−¥138.00`（红色）
  - 付款时间：`2026-01-20 14:32`
  - 交易状态：「支付成功」
  - 交易单号：`4200002026012000881234`

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of SiXin (私信通) Pay (私信通支付) success notification in Chinese. The recipient is "诚品优选商城", amount is "-¥138.00" in large red bold font, payment time "2026-01-20 14:32", transaction status "支付成功" with green check, transaction number "4200002026012000881234". Green SiXin (私信通) brand theme (#07c160), clean white card layout, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，私信通支付成功通知。收款方"诚品优选商城"，金额"-¥138.00"（红色大字），付款时间 2026-01-20 14:32，状态"支付成功"（绿色对勾），交易单号 4200002026012000881234。品牌主绿，状态栏 9:41，1080x1920。
```

---

#### ~~📷 E1-5 ｜ 诚品优选自营物流详情页~~
- **证据类型**：`logistics_tracking`
- **必带文字**：
  - 快递单号：`CP0012345678901`
  - 物流公司：「诚品优选自营物流」
  - 关键节点：
    - `2026-01-22 11:08` 派送中，配送员「张师傅 138-0011-2233」
    - `2026-01-22 14:25` 已签收
  - 状态：「已完成」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 诚品优选 B2C (ChengPin) logistics tracking page in Chinese. Tracking number "CP0012345678901", carrier "诚品优选自营物流". Key events: "2026-01-22 11:08 派送中 配送员 张师傅 138-0011-2233" and "2026-01-22 14:25 已签收" with green checkmark. ChengPin red theme, status "已完成" at top, top status bar 9:41, 100% battery. Timeline-style UI with dots and connecting line, clean modern Chinese app design, 1080x1920.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，诚品优选自营物流详情页。快递单号 CP0012345678901，物流公司"诚品优选自营物流"。时间线节点：2026-01-22 11:08 派送中（配送员张师傅 138-0011-2233）、2026-01-22 14:25 已签收（绿色对勾）。状态"已完成"，状态栏 9:41，1080x1920。
```

---

#### 📷 E1-6a ｜ 饼干实物照片 1（发霉特写）
- **证据类型**：`other`
- **必带文字**：无（纯实物拍摄）

**主 Prompt（英文 · 推荐）**：
```
A photorealistic close-up photograph taken with modern flagship smartphone, showing an opened transparent plastic bag of butter cookies with visible white and green mold spots on multiple cookies. The bag is half-opened, sitting on a beige fabric tablecloth, natural indoor lighting. Several cookies have obvious fuzzy white mold growth and some greenish discoloration. The yellow cookie color is dull. modern flagship smartphone camera watermark style, no filter, no beautification, raw realistic photo, sharp focus, 1080x1080 or 1080x1920.
```

**中文 Prompt（备用）**：
```
modern flagship smartphone 实物近照：一袋透明包装的黄油曲奇已被拆开，多块曲奇上清晰可见白色和绿色的霉斑。袋子半开，放在米色布艺桌布上，自然室内光。部分曲奇长出明显毛茸茸的白色霉菌、个别呈绿色。原黄色曲奇色泽发暗。无滤镜、无美颜、原片质感、对焦清晰，1080x1080。
```

---

#### 📷 E1-6b ｜ 包装生产日期特写
- **证据类型**：`other`
- **必带文字**：
  - 「生产日期：2025/09/01」
  - 「保质期：12 个月」
  - 「原产国：北欧某国」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic close-up modern flagship smartphone photo of the back of an imported butter cookie package. Clear Chinese text on white packaging: "生产日期：2025/09/01", "保质期：12 个月", "原产国：北欧某国". Other text includes ingredients list and barcode (partially blurred). The photo is shot at slight angle, natural indoor lighting, sharp focus on date text, modern flagship smartphone camera style, no filter, 1080x1080.
```

**中文 Prompt（备用）**：
```
modern flagship smartphone 实物近照：进口曲奇包装背面特写。包装上清晰印刷中文："生产日期：2025/09/01"、"保质期：12 个月"、"原产国：北欧某国"。其余文字为配料表和条形码（自然模糊）。微微倾斜角度，室内自然光，对焦在日期文字上，原片质感，1080x1080。
```

---

### 场景 2 ｜ 网购相机虚假宣传 —— 「广告法 56 条 · 退一赔三」

#### 📷 E2-1 ｜ 惠购优品订单详情
- **证据类型**：`product_order`
- **必带文字**：
  - 订单号：`PD202602100077`
  - 商品名：「影匠 X9 全新国行 官方授权」
  - 金额：`¥14800.00`
  - 状态：「已签收」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 惠购优品 (HiGou) order detail page in Chinese. Order number "PD202602100077", product name "影匠 X9 全新国行 官方授权", amount "¥14800.00" in large red font, status "已签收" with check icon. 惠购优品 (HiGou)'s signature orange-pink theme (品牌主橙红), white card with 影匠 camera product image. Top status bar 9:41, full signal, 100% battery. Clean Chinese e-commerce app UI, 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，惠购优品订单详情。订单号 PD202602100077，商品名"影匠 X9 全新国行 官方授权"，金额"¥14800.00"（红色大字），状态"已签收"。品牌主橙红，1080x1920。
```

---

#### 📷 E2-2 ｜ 私信通支付凭证（14800 元）
- **证据类型**：`payment_record`
- **必带文字**：
  - 收款方：「惠购优品平台商户」
  - 金额：`−¥14800.00`
  - 付款时间：`2026-02-10 21:45`
  - 状态：「支付成功」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of SiXin (私信通) Pay success notification in Chinese. Recipient "惠购优品平台商户", amount "-¥14800.00" in large red bold font, payment time "2026-02-10 21:45", status "支付成功" with green check. 品牌主绿 (#07c160), white card layout, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，私信通支付凭证。收款方"惠购优品平台商户"，金额"-¥14800.00"（红色大字），付款时间 2026-02-10 21:45，状态"支付成功"（绿色对勾）。品牌主绿，1080x1920。
```

---

#### 📷 E2-3 ｜ 商家聊天 - 「假一赔十」承诺
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 对方名称：「XX 数码旗舰店主」
  - 时间戳：`2026-02-09 18:20`
  - 买家消息：「是正品国行吗？有没有授权？」
  - 商家回复：「亲我们是影匠官方授权店，假一赔十，放心下单」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 惠购优品 (HiGou) merchant chat in Chinese. Merchant name "XX 数码旗舰店主" at top, time 2026-02-09 18:20. Buyer's message on right "是正品国行吗？有没有授权？". Merchant's reply on left in green bubble "亲我们是影匠官方授权店，假一赔十，放心下单". 惠购优品 (HiGou) theme, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，惠购优品商家聊天。商家名"XX 数码旗舰店主"，时间 2026-02-09 18:20。买家右气泡："是正品国行吗？有没有授权？"，商家左气泡（绿色）："亲我们是影匠官方授权店，假一赔十，放心下单"。1080x1920。
```

---

#### 📷 E2-4 ｜ 商家聊天 - 拒绝售后
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 时间戳：`2026-02-26 09:15`
  - 买家消息：「机身有划痕，保修卡空白，要求退一赔三」
  - 商家回复：「亲，商品已签收 15 天，不支持无理由退货哦」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 惠购优品 (HiGou) merchant chat. Time 2026-02-26 09:15. Buyer message on right: "机身有划痕，保修卡空白，要求退一赔三". Merchant reply on left: "亲，商品已签收 15 天，不支持无理由退货哦". 惠购优品 (HiGou) theme, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，惠购优品商家聊天。时间 2026-02-26 09:15。买家右气泡："机身有划痕，保修卡空白，要求退一赔三"，商家左气泡："亲，商品已签收 15 天，不支持无理由退货哦"。1080x1920。
```

---

#### 📷 E2-5 ｜ 商品宣传截图 1
- **证据类型**：`other`
- **必带文字**：
  - 标题大字：「全新国行 官方授权 假一赔十」
  - 副标题：「影匠 X9 II 微单相机」
  - 价格：`¥14800`

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of a 惠购优品 (HiGou) product detail page in Chinese. Large product title "全新国行 官方授权 假一赔十", subtitle "影匠 X9 II 微单相机", price "¥14800" in red. Background is a product photo of a 影匠 X9 II camera. 惠购优品 (HiGou) orange-pink theme, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，惠购优品商品详情页。大标题"全新国行 官方授权 假一赔十"，副标题"影匠 X9 II 微单相机"，价格"¥14800"（红色）。背景为 影匠 X9 II 相机产品图。1080x1920。
```

---

#### 📷 E2-6 ｜ 商品宣传截图 2 - 商家回复
- **证据类型**：`other`
- **必带文字**：
  - 评论区提问：「是正品吗？」
  - 商家回复（带「商家」橙色标签）：「我们是官方授权店，假一赔十，支持专柜验货」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 惠购优品 (HiGou) product review section. A buyer question "是正品吗？" with merchant reply in orange "商家" tag "我们是官方授权店，假一赔十，支持专柜验货". 惠购优品 (HiGou) theme, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，惠购优品商品评论区。买家问"是正品吗？"，商家回复（橙色"商家"标签）："我们是官方授权店，假一赔十，支持专柜验货"。1080x1920。
```

---

#### 📷 E2-7a ｜ 机身划痕特写
- **证据类型**：`other`
- **必带文字**：无

**主 Prompt（英文 · 推荐）**：
```
A photorealistic close-up modern flagship smartphone photo of a black 影匠 X9 II camera body with visible scratch marks and scuffs on the top plate near the hot shoe and mode dial. The scratches are clearly visible as silver-white lines on the black painted surface. Indoor natural lighting, sharp focus, no filter, no beautification, raw photo style, 1080x1080.
```

**中文 Prompt（备用）**：
```
modern flagship smartphone 实物近照：黑色 影匠 X9 II 相机机身顶部特写。热靴和模式转盘附近的黑色漆面有清晰可见的银白色划痕和磨损。室内自然光，对焦清晰，无滤镜无美颜，1080x1080。
```

---

#### 📷 E2-7b ｜ 序列号不一致特写
- **证据类型**：`other`
- **必带文字**：
  - 包装序列号标签：「SN: 2012345」
  - 机身底部序列号：「SN: 2098765」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone photo showing two white product labels side by side on a clean white surface. The left label says "外包装序列号 SN: 2012345" and the right label (camera body) says "机身底部序列号 SN: 2098765". Both are printed in standard industrial fonts. A red arrow hand-drawn on the photo (made with phone's markup tool) circles the two different numbers, with handwritten red text "序列号不一致！！" above. Indoor lighting, sharp focus, 1080x1080.
```

**中文 Prompt（备用）**：
```
modern flagship smartphone 实物近照：白色桌面上并排两张白色产品标签。左侧"外包装序列号 SN: 2012345"，右侧"机身底部序列号 SN: 2098765"。照片上用手机自带标记工具手绘红色箭头圈出两个不同的数字，上方手写红字"序列号不一致！！"。室内光，对焦清晰，1080x1080。
```

---

### 场景 3 ｜ 家装服务违约 —— 「民法典 577 条 · 服务合同」

#### 📷 E3-1 ｜ 装修合同关键页
- **证据类型**：`product_order`
- **必带文字**：
  - 合同标题：「室内装饰装修工程施工合同」
  - 甲方：「张先生」
  - 乙方：「XX 装饰工程有限公司」
  - 合同金额：`¥80000.00（人民币捌万元整）`
  - 开工日期：`2025-12-01`
  - 竣工日期：`2026-03-01`
  - 底部签字栏（双方签字 + 红手印）

**主 Prompt（英文 · 推荐）**：
```
A photorealistic top-down photograph of a printed Chinese home decoration contract on white A4 paper, placed on a wooden desk. Contract title "室内装饰装修工程施工合同" in bold black text. Key fields visible: 甲方 "张先生", 乙方 "XX 装饰工程有限公司", 合同金额 "¥80000.00（人民币捌万元整）" in red, 开工日期 "2025-12-01", 竣工日期 "2026-03-01". The bottom has two signature lines with handwritten Chinese signatures and red fingerprint stamps. Natural indoor lighting, slight angle, sharp focus on text, 1080x1920.
```

**中文 Prompt（备用）**：
```
实物近照俯拍：木桌上放着 A4 白纸打印的中文装修合同。标题"室内装饰装修工程施工合同"黑色加粗。可见字段：甲方"张先生"、乙方"XX 装饰工程有限公司"、合同金额"¥80000.00（人民币捌万元整）"（红色）、开工日期 2025-12-01、竣工日期 2026-03-01。底部双方签字栏有手写签名和红色指纹印。室内自然光，略微倾斜，对焦在文字上，1080x1920。
```

---

#### 📷 E3-2 ｜ 首期款支付凭证
- **证据类型**：`payment_record`
- **必带文字**：
  - 收款方：「XX 装饰工程有限公司」
  - 金额：`−¥30000.00`
  - 付款时间：`2025-11-28 10:08`
  - 备注：「装修首期款」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of SiXin (私信通) Pay success notification in Chinese. Recipient "XX 装饰工程有限公司", amount "-¥30000.00" in red bold, payment time "2025-11-28 10:08", remark "装修首期款". 品牌主绿, white card layout, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，私信通支付凭证。收款方"XX 装饰工程有限公司"，金额"-¥30000.00"（红色），付款时间 2025-11-28 10:08，备注"装修首期款"。品牌主绿，1080x1920。
```

---

#### 📷 E3-3 ｜ 中期款支付凭证（延迟 1 个月）
- **证据类型**：`payment_record`
- **必带文字**：
  - 收款方：「XX 装饰工程有限公司」
  - 金额：`−¥30000.00`
  - 付款时间：`2026-01-20 15:32`
  - 备注：「装修中期款（比合同约定晚 1 个月）」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of SiXin (私信通) Pay success notification. Recipient "XX 装饰工程有限公司", amount "-¥30000.00" in red, payment time "2026-01-20 15:32", remark "装修中期款（比合同约定晚 1 个月）". 品牌主绿, white card, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，私信通支付凭证。收款方"XX 装饰工程有限公司"，金额"-¥30000.00"（红色），付款时间 2026-01-20 15:32，备注"装修中期款（比合同约定晚 1 个月）"。1080x1920。
```

---

#### 📷 E3-4 ｜ 项目经理聊天 1 - 承诺延期
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 对方名称：「王工（项目总监）」
  - 时间戳：`2025-12-25 09:18`
  - 买家消息：「不是说 12 月 1 号开工吗？都 12 月 25 了还没进场」
  - 对方回复：「师傅手头还有别的活，可能要延后几天」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of SiXin (私信通) chat. Contact name "王工（项目总监）" at top, time 2025-12-25 09:18. Buyer message on right "不是说 12 月 1 号开工吗？都 12 月 25 了还没进场". Reply on left "师傅手头还有别的活，可能要延后几天". SiXin (私信通) light theme, white bubbles, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，私信通聊天。对方"王工（项目总监）"，时间 2025-12-25 09:18。买家右气泡："不是说 12 月 1 号开工吗？都 12 月 25 了还没进场"，对方左气泡："师傅手头还有别的活，可能要延后几天"。1080x1920。
```

---

#### 📷 E3-5 ｜ 项目经理聊天 2 - 虚假承诺
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 时间戳：`2026-02-18 20:05`
  - 买家消息：「卫生间防水做好了吗？什么时候能贴砖？」
  - 对方回复：「已经做好了，师傅手艺你放心，闭水试验 24h 没问题」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of SiXin (私信通) chat with "王工". Time 2026-02-18 20:05. Buyer message "卫生间防水做好了吗？什么时候能贴砖？". Reply "已经做好了，师傅手艺你放心，闭水试验 24h 没问题". SiXin (私信通) light theme, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，与"王工"私信通聊天。时间 2026-02-18 20:05。买家右气泡："卫生间防水做好了吗？什么时候能贴砖？"，对方左气泡："已经做好了，师傅手艺你放心，闭水试验 24h 没问题"。1080x1920。
```

---

#### 📷 E3-6a ｜ 未完工橱柜特写
- **证据类型**：`other`
- **必带文字**：无

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone photo of a half-finished kitchen with exposed particle board cabinets, missing cabinet doors, loose wires hanging out, dust and construction debris on the floor. The wall has unfinished paint and exposed cement. The photo is shot from standing perspective showing the full mess. Indoor natural lighting, no beautification, 1080x1080 or 1080x1920.
```

**中文 Prompt（备用）**：
```
modern flagship smartphone 实物照：未完工的厨房，裸露的刨花板橱柜体、柜门缺失、电线外露、地面灰尘和建筑垃圾。墙面有未粉刷的水泥。站立视角拍摄完整混乱场面，室内自然光，无美颜，1080x1080。
```

---

#### 📷 E3-6b ｜ 卫生间防水起泡特写
- **证据类型**：`other`
- **必带文字**：无

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone close-up photo of a bathroom floor with bad waterproofing. The grey waterproof coating is bubbling and peeling off in multiple spots, water seeping up through cracks. The grouting between tiles is incomplete. A handwritten red arrow on the photo (drawn with phone markup) points to the bubbles with text "防水起泡 偷工减料" in red. Indoor lighting, sharp focus, 1080x1080.
```

**中文 Prompt（备用）**：
```
modern flagship smartphone 实物近照：卫生间地面防水工程质量问题。灰色防水涂层多处起泡、脱落，裂缝处有水渗出。瓷砖填缝不完整。照片上用手机标记工具手绘红色箭头指向起泡处，红字标注"防水起泡 偷工减料"。室内光，对焦清晰，1080x1080。
```

---

#### 📷 E3-6c ｜ 空无一人的施工现场
- **证据类型**：`other`
- **必带文字**：无

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone photo of an empty, abandoned construction site inside a residential apartment. Dust on the floor, tools left scattered, half-painted walls, no workers visible. A wall calendar in the background shows "March 2026" with a red circle hand-drawn on the 30th (taken with phone markup). Natural daylight from window, no filter, 1080x1080 or 1080x1920.
```

**中文 Prompt（备用）**：
```
modern flagship smartphone 实物照：居民楼内空无一人的施工现场。地面灰尘、工具散落、墙面未完工、看不到工人。背景墙上挂历显示 2026 年 3 月，3 月 30 日被手机标记工具手绘红圈圈出。窗户自然光，无滤镜，1080x1920。
```

---

### 场景 4 ｜ 外卖吃出苍蝇 —— 「食安法 148 条 · 最低 1000 元」

#### 📷 E4-1 ｜ 即享外卖订单详情
- **证据类型**：`product_order`
- **必带文字**：
  - 订单号：`JX202602180066`
  - 商家名：「XX 鸡汁饭（XX 路店）」
  - 商品：「鸡汁饭（大份）× 1」
  - 金额：`¥28.00`
  - 配送时间：`2026-02-18 12:15`

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of JXG (即享外卖) order detail page in Chinese. Order number "JX202602180066", merchant "XX 鸡汁饭（XX 路店）", product "鸡汁饭（大份）× 1", amount "¥28.00" in red, delivery time "2026-02-18 12:15". JXG (即享外卖)'s signature yellow theme (#ffc300), white card with food image. Top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，即享外卖订单详情。订单号 JX202602180066，商家"XX 鸡汁饭（XX 路店）"，商品"鸡汁饭（大份）× 1"，金额"¥28.00"（红色），送达时间 2026-02-18 12:15。品牌主黄，1080x1920。
```

---

#### 📷 E4-2 ｜ 私信通支付凭证（28 元）
- **证据类型**：`payment_record`
- **必带文字**：
  - 收款方：「即享外卖平台商户」
  - 金额：`−¥28.00`
  - 付款时间：`2026-02-18 12:03`
  - 状态：「支付成功」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of SiXin (私信通) Pay success notification. Recipient "即享外卖平台商户", amount "-¥28.00" in red, time "2026-02-18 12:03", status "支付成功" with green check. 品牌主绿, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，私信通支付凭证。收款方"即享外卖平台商户"，金额"-¥28.00"（红色），付款时间 2026-02-18 12:03，状态"支付成功"。品牌主绿，1080x1920。
```

---

#### 📷 E4-3 ｜ 商家聊天 - 拒绝足额赔偿
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 对方名称：「XX 鸡汁饭 客服」
  - 时间戳：`2026-02-18 13:22`
  - 买家消息：「吃到一只完整苍蝇，要求 1000 元赔偿」
  - 商家回复：「亲，最多退您这份 28 元 + 10 元无门槛券，已经是我们最大诚意了」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of merchant chat in JXG (即享外卖) app. Merchant name "XX 鸡汁饭 客服" at top, time 2026-02-18 13:22. Buyer message on right: "吃到一只完整苍蝇，要求 1000 元赔偿". Merchant reply on left in white bubble: "亲，最多退您这份 28 元 + 10 元无门槛券，已经是我们最大诚意了". JXG (即享外卖), top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，即享外卖商家聊天。商家名"XX 鸡汁饭 客服"，时间 2026-02-18 13:22。买家右气泡："吃到一只完整苍蝇，要求 1000 元赔偿"，商家左气泡："亲，最多退您这份 28 元 + 10 元无门槛券，已经是我们最大诚意了"。1080x1920。
```

---

#### 📷 E4-4 ｜ 即享外卖平台客服聊天
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 对方名称：「即享客服 03」
  - 时间戳：`2026-02-18 14:50`
  - 买家消息：「平台是否对商家有食品安全监管责任？我要 1000 元赔偿」
  - 客服回复：「亲，已记录您的反馈，我们会督促商家尽快与您联系，平台会跟进处理」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of JXG (即享外卖) service chat. Agent "即享客服 03", time 2026-02-18 14:50. Buyer message on right: "平台是否对商家有食品安全监管责任？我要 1000 元赔偿". Agent reply on left: "亲，已记录您的反馈，我们会督促商家尽快与您联系，平台会跟进处理". JXG (即享外卖), top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，即享外卖平台客服聊天。客服"即享客服 03"，时间 2026-02-18 14:50。买家右气泡："平台是否对商家有食品安全监管责任？我要 1000 元赔偿"，客服左气泡："亲，已记录您的反馈，我们会督促商家尽快与您联系，平台会跟进处理"。1080x1920。
```

---

#### 📷 E4-5a ｜ 饭菜里苍蝇特写
- **证据类型**：`other`
- **必带文字**：无

**主 Prompt（英文 · 推荐）**：
```
A photorealistic close-up modern flagship smartphone photo of an open Chinese claypot of 鸡汁饭 (braised chicken with yellow sauce), with a full dead fly lying on top of the chicken pieces. The fly's wings, body, and legs are clearly visible. The yellow sauce and potato pieces surround it. The claypot is on a wooden dining table with steam still slightly visible. modern flagship smartphone camera style, no filter, indoor dining lighting, sharp focus, 1080x1080.
```

**中文 Prompt（备用）**：
```
modern flagship smartphone 实物近照：一锅打开的鸡汁饭，鸡肉块上有一只完整的死苍蝇。苍蝇的翅膀、身体、腿清晰可见。黄色酱汁和土豆块包围着它。砂锅放在木制餐桌上，还能看到轻微的水蒸气。modern flagship smartphone 相机风格，无滤镜，餐厅室内光，对焦清晰，1080x1080。
```

---

#### 📷 E4-5b ｜ 整份饭现场
- **证据类型**：`other`
- **必带文字**：
  - 即享外卖外卖小票（顶部覆盖）：

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone photo of the full Chinese claypot meal of 鸡汁饭 on a wooden table, with the white JXG (即享外卖) delivery receipt placed next to it. The receipt shows order number "JX202602180066", amount "28.00元", merchant "XX 鸡汁饭", delivery time "2026-02-18 12:15". The claypot is half-eaten, showing the inside contents. A red arrow drawn on the photo (with phone markup) points to the pot. Indoor lighting, 1080x1920.
```

**中文 Prompt（备用）**：
```
modern flagship smartphone 实物照：木制餐桌上整份鸡汁饭砂锅，旁边放着即享外卖外卖白色小票。小票上清晰可见订单号 JX202602180066、金额 28.00 元、商家"XX 鸡汁饭"、送达时间 2026-02-18 12:15。砂锅被吃了一半，可见内部内容。照片上手绘红色箭头（手机标记）指向砂锅。室内光，1080x1920。
```

---

### 场景 5 ｜ 健身房跑路 —— 「预付卡跑路 · 群体维权」

#### 📷 E5-1 ｜ 健身房入会合同
- **证据类型**：`product_order`
- **必带文字**：
  - 标题：「XX 健身俱乐部会员入会协议」
  - 会员名：「赵女士」
  - 会籍类型：「一年期至尊卡」
  - 金额：`¥3000.00`
  - 有效期：`2025-10-01 至 2026-10-01`
  - 门店地址：「XX 市 XX 区 XX 路 88 号 XX 广场 3 楼」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic top-down photograph of a printed Chinese gym membership contract on white A4 paper. Title "XX 健身俱乐部会员入会协议" in bold black. Key fields: 会员名 "赵女士", 会籍类型 "一年期至尊卡", 金额 "¥3000.00" in red, 有效期 "2025-10-01 至 2026-10-01", 门店地址 "XX 市 XX 区 XX 路 88 号 XX 广场 3 楼". Bottom has signature line and red company stamp. The paper sits on a desk, natural lighting, slight angle, sharp focus, 1080x1920.
```

**中文 Prompt（备用）**：
```
实物俯拍：白纸 A4 打印的中文健身房入会合同。标题"XX 健身俱乐部会员入会协议"黑色加粗。关键字段：会员名"赵女士"、会籍类型"一年期至尊卡"、金额"¥3000.00"（红色）、有效期 2025-10-01 至 2026-10-01、门店地址"XX 市 XX 区 XX 路 88 号 XX 广场 3 楼"。底部有签字栏和红色公司印章。室内光，1080x1920。
```

---

#### 📷 E5-2 ｜ 刷卡 / 私信通支付凭证
- **证据类型**：`payment_record`
- **必带文字**：
  - 收款方：「XX 健身俱乐部」
  - 金额：`−¥3000.00`
  - 付款时间：`2025-09-28 19:12`
  - 备注：「年卡会费」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of SiXin (私信通) Pay success notification. Recipient "XX 健身俱乐部", amount "-¥3000.00" in red, time "2025-09-28 19:12", remark "年卡会费". 品牌主绿, white card, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，私信通支付凭证。收款方"XX 健身俱乐部"，金额"-¥3000.00"（红色），付款时间 2025-09-28 19:12，备注"年卡会费"。品牌主绿，1080x1920。
```

---

#### 📷 E5-3 ｜ 店长聊天 - 「绝对跑不了」
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 对方名称：「XX 健身 李店长」
  - 时间戳：`2025-09-25 14:08`
  - 买家消息：「听说你们经营不太稳，这卡能办吗？」
  - 对方回复：「放心吧姐妹，我们背后有 XX 集团，绝对跑不了，全国 200 多家店」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of SiXin (私信通) chat. Contact "XX 健身 李店长" at top, time 2025-09-25 14:08. Buyer message on right "听说你们经营不太稳，这卡能办吗？". Reply on left "放心吧姐妹，我们背后有 XX 集团，绝对跑不了，全国 200 多家店". SiXin (私信通) light theme, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，私信通聊天。对方"XX 健身 李店长"，时间 2025-09-25 14:08。买家右气泡："听说你们经营不太稳，这卡能办吗？"，对方左气泡："放心吧姐妹，我们背后有 XX 集团，绝对跑不了，全国 200 多家店"。1080x1920。
```

---

#### 📷 E5-4a ｜ 跑路现场 1 - 关门的门店
- **证据类型**：`other`
- **必带文字**：
  - 门上 A4 通知：「尊敬的会员：因经营调整，本店即日起暂停营业，会籍问题请致电 400-XXX-XXXX」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone photo of a closed gym storefront with glass doors. A white A4 paper notice is taped to the door reading "尊敬的会员：因经营调整，本店即日起暂停营业，会籍问题请致电 400-XXX-XXXX". The gym interior is dimly visible behind the glass, with dust on equipment. A hand-drawn red "X" mark on the photo (with phone markup) is over the door. Daytime outdoor natural light, sharp focus on the notice text, 1080x1920.
```

**中文 Prompt（备用）**：
```
modern flagship smartphone 实物照：紧闭的健身房玻璃门店面。门上贴着白色 A4 通知："尊敬的会员：因经营调整，本店即日起暂停营业，会籍问题请致电 400-XXX-XXXX"。玻璃后隐约可见昏暗的店内，器械上有灰尘。照片上手绘红色 X 标记（手机标记）覆盖在门上。白天室外自然光，对焦在通知文字上，1080x1920。
```

---

#### 📷 E5-4b ｜ 商户点评 / 12345 投诉截图
- **证据类型**：`other`
- **必带文字**：
  - 标题：「XX 健身 XX 路店」
  - 评分：「★ 1.2」
  - 评价数量：「近期 47 条投诉」
  - 部分评价：「1 月 20 日 138****1234：骗子公司！办卡 3 个月就跑了！」
  - 部分评价：「1 月 22 日 139****5678：一起维权！加群 XXXXXX」
  - 部分评价：「1 月 24 日 156****9012：老板跑路了，已经报警」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 商户点评 merchant page in Chinese. Merchant name "XX 健身 XX 路店" at top, rating "★ 1.2" in red, "近期 47 条投诉" tag. Review list shows three recent negative reviews: "1 月 20 日 138****1234：骗子公司！办卡 3 个月就跑了！", "1 月 22 日 139****5678：一起维权！加群 XXXXXX", "1 月 24 日 156****9012：老板跑路了，已经报警". Each review is marked with 1 star in red. White background, clean Chinese app UI, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，商户点评商户页。顶部"XX 健身 XX 路店"，评分"★ 1.2"（红色），标签"近期 47 条投诉"。评论列表 3 条差评："1 月 20 日 138****1234：骗子公司！办卡 3 个月就跑了！"、"1 月 22 日 139****5678：一起维权！加群 XXXXXX"、"1 月 24 日 156****9012：老板跑路了，已经报警"。每条评论均 1 星红色。白底中文 UI，1080x1920。
```

---

### 场景 6 ｜ 商家反证答辩 —— 「反向维权 · 案件模式 = respond」

#### 📷 E6-1 ｜ 海淘集市订单详情
- **证据类型**：`product_order`
- **必带文字**：
  - 订单号：`HT202601050123`
  - 商品名：「法式连衣裙 S 码 米白色」
  - 金额：`¥299.00`
  - 下单时间：`2026-01-05 20:14`
  - 状态：「交易成功」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 海淘集市 order detail page in Chinese. Order number "HT202601050123", product "法式连衣裙 S 码 米白色", amount "¥299.00" in red, order time "2026-01-05 20:14", status "交易成功" with green check. 海淘集市's signature orange theme (#ff5000), white card with white dress product image. Top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，海淘集市订单详情。订单号 HT202601050123，商品名"法式连衣裙 S 码 米白色"，金额"¥299.00"（红色），下单时间 2026-01-05 20:14，状态"交易成功"。品牌主橙，1080x1920。
```

---

#### 📷 E6-2 ｜ 物流详情 - 1 月 8 日签收
- **证据类型**：`logistics_tracking`
- **必带文字**：
  - 快递单号：`SD1234567890123`
  - 物流公司：「速达快递」
  - 关键节点：
    - `2026-01-07 18:32` 派送中
    - `2026-01-08 11:25` 已签收（本人签收）

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of TongYi (通驿物流) logistics tracking page in Chinese. Tracking number "SD1234567890123", carrier "速达快递". Key events: "2026-01-07 18:32 派送中" and "2026-01-08 11:25 已签收（本人签收）" with green checkmark. White card with timeline UI, dots and connecting line, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，通驿物流详情页。快递单号 SD1234567890123，物流公司"速达快递"。时间线节点：2026-01-07 18:32 派送中、2026-01-08 11:25 已签收（本人签收）（绿色对勾）。白底时间线 UI，1080x1920。
```

---

#### 📷 E6-3 ｜ 买家投诉聊天 - 「退一赔三」诉求
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 对方名称：「小仙女 🌸」
  - 时间戳：`2026-01-26 14:32`
  - 买家消息：「穿了 3 天就起球、有异味，强烈要求退一赔三共 1196 元！」
  - 商家回复：「亲，签收已 18 天，超出 7 天无理由期。请提供质检报告」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 海淘集市 站内信 chat in Chinese. Buyer name "小仙女 🌸" at top, time 2026-01-26 14:32. Buyer message on right: "穿了 3 天就起球、有异味，强烈要求退一赔三共 1196 元！". Merchant reply on left: "亲，签收已 18 天，超出 7 天无理由期。请提供质检报告". 海淘集市 orange theme, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，海淘集市站内信聊天。买家"小仙女 🌸"，时间 2026-01-26 14:32。买家右气泡："穿了 3 天就起球、有异味，强烈要求退一赔三共 1196 元！"，商家左气泡："亲，签收已 18 天，超出 7 天无理由期。请提供质检报告"。品牌主橙，1080x1920。
```

---

#### 📷 E6-4 ｜ **关键反证 1** - 买家灵感笔记晒单
- **证据类型**：`other`
- **必带文字**：
  - 用户名：「小仙女 🌸」
  - 发布时间：`2026-01-12 18:30`
  - 笔记标题：「闺蜜聚会穿搭｜这条裙子绝了！」
  - 配文：「新入手的法式连衣裙，参加闺蜜聚会超好看 @XX 店铺」
  - 配图：买家穿着同款米白色连衣裙的聚会照（3 张拼图）
  - 底部互动：❤️ 1.2k  💬 286  ⭐ 532

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 灵感笔记 (LinGan Notes) post in Chinese. Username "小仙女 🌸" at top, post time "2026-01-12 18:30". Post title "闺蜜聚会穿搭｜这条裙子绝了！", caption "新入手的法式连衣裙，参加闺蜜聚会超好看 @XX 店铺". Image grid shows 3 photos of a young woman wearing a white French-style dress at a friend gathering, smiling, well-styled hair and makeup. Engagement metrics at bottom: ❤️ 1.2k, 💬 286, ⭐ 532. LinGan red theme (#ff2442), top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，灵感笔记笔记。用户"小仙女 🌸"，发布时间 2026-01-12 18:30。笔记标题"闺蜜聚会穿搭｜这条裙子绝了！"，正文"新入手的法式连衣裙，参加闺蜜聚会超好看 @XX 店铺"。配图 3 宫格：一位年轻女性穿着米白色法式连衣裙参加闺蜜聚会，妆容精致、发型讲究、笑容灿烂。底部互动：❤️ 1.2k  💬 286  ⭐ 532。灵感笔记红主题，1080x1920。
```

---

#### 📷 E6-5 ｜ **关键反证 2** - 质检报告
- **证据类型**：`other`
- **必带文字**：
  - 标题：「商品质量检验报告」
  - 报告编号：`QT-2025-A1-0882`
  - 委托单位：「XX 服饰有限公司」
  - 检验结论：「经抽样检验，所检项目符合 GB/T 23328-2009《机织学生服》、GB 18401-2010《国家纺织产品基本安全技术规范》标准要求，判定合格」
  - 检验日期：`2025-12-10`
  - 底部：红色 CMA 印章 + 检验员签字

**主 Prompt（英文 · 推荐）**：
```
A photorealistic top-down photograph of a printed Chinese quality inspection report on white A4 paper with red border. Title "商品质量检验报告" in bold black at top, report number "QT-2025-A1-0882", 委托单位 "XX 服饰有限公司", 检验结论 "经抽样检验，所检项目符合 GB/T 23328-2009《机织学生服》、GB 18401-2010《国家纺织产品基本安全技术规范》标准要求，判定合格" in a highlighted box, 检验日期 "2025-12-10". Bottom has red CMA stamp and signature. Slight angle, natural lighting, sharp focus, 1080x1920.
```

**中文 Prompt（备用）**：
```
实物俯拍：白纸 A4 打印的中文质量检验报告，带红色边框。标题"商品质量检验报告"顶部黑色加粗，报告编号 QT-2025-A1-0882，委托单位"XX 服饰有限公司"，检验结论在框中显示："经抽样检验，所检项目符合 GB/T 23328-2009《机织学生服》、GB 18401-2010《国家纺织产品基本安全技术规范》标准要求，判定合格"，检验日期 2025-12-10。底部红色 CMA 印章和检验员签字。略微倾斜，室内光，1080x1920。
```

---

#### 📷 E6-6 ｜ **关键反证 3** - 18 天才投诉的聊天记录
- **证据类型**：`chat_screenshot`
- **必带文字**：
  - 对方名称：「小仙女 🌸」
  - 时间戳：`2026-01-26 14:30`（与 E6-3 衔接）
  - 对方消息：「亲在吗？」
  - 商家回复：「在的亲，请问有什么问题？」
  - 对方消息：「在的，我穿了几次起球了」
  - 商家回复：「亲，请问具体是哪天收到的？」
  - 对方消息：「1 月 8 号」商家回复：「1 月 8 号到现在 18 天了，请问中间一直有问题为什么没有反馈？」

**主 Prompt（英文 · 推荐）**：
```
A photorealistic modern flagship smartphone screenshot of 海淘集市 站内信 chat. Buyer "小仙女 🌸", time 2026-01-26 14:30. Conversation: buyer says "亲在吗？", merchant replies "在的亲，请问有什么问题？", buyer "在的，我穿了几次起球了", merchant "亲，请问具体是哪天收到的？", buyer "1 月 8 号", merchant "1 月 8 号到现在 18 天了，请问中间一直有问题为什么没有反馈？". 海淘集市 orange theme, top status bar 9:41, 100% battery. 1080x1920, pill notch visible.
```

**中文 Prompt（备用）**：
```
旗舰手机截图，海淘集市站内信聊天。买家"小仙女 🌸"，时间 2026-01-26 14:30。对话：买家"亲在吗？"，商家"在的亲，请问有什么问题？"，买家"在的，我穿了几次起球了"，商家"亲，请问具体是哪天收到的？"，买家"1 月 8 号"，商家"1 月 8 号到现在 18 天了，请问中间一直有问题为什么没有反馈？"。品牌主橙，1080x1920。
```

---

## 三、通用使用建议

### 1. 文字渲染小技巧
- 现代模型（DALL·E 3 / Midjourney v6 / SD3 / Seedream 3.0）对**英文 + 数字**渲染最好
- **中文文字**建议先生成"半成品"截图（UI 框架 + 占位文字），再用工具二次合成
- 替代方案：先用模型生成纯视觉画面，再用 **Figma / 创客贴 / Photoshop** 在画面上叠加中文文字
- 推荐工具链：**Midjourney v6 出氛围图 → Photoshop 叠中文 → PNG 导出**

### 2. 尺寸选择
- 手机截图类（E1-1 ~ E6-6 中除 E5-1、E6-5、E1-6a/b、E2-7a/b、E3-6a/b/c、E4-5a/b、E5-4a、E6-5 外）：**1080 × 1920**（9:16 portrait）
- 实物 / 合同照片类：可选 **1080 × 1080**（1:1）或 **1080 × 1920**（9:16 修长版）

### 3. 风格一致性
- 全部素材使用同一手机型号（modern flagship smartphone）
- 全部素材保持状态栏时间统一为 `9:41`（国际品牌样张时间）
- 中文 UI 元素使用 系统默认中文字体

### 4. 批量生成工作流
- Step 1：先选 1-2 张最具代表性的 prompt 测试模型效果
- Step 2：确认中文渲染质量、UI 风格、配色符合预期
- Step 3：批量生成剩余 33 张，使用相同 seed 范围保证风格一致
- Step 4：使用 Photoshop / Figma 批量二次合成中文文字
- Step 5：人工校对关键数字（金额、订单号、日期）

### 5. 法律合规
- 所有订单号、手机号、银行卡号均为**虚构**，避免与真实用户数据冲突
- 商家名、店铺地址、人物头像都使用**虚构信息**
- 演示素材**仅供产品展示使用**，不要用于真实维权

---

## 四、Prompt 复用速查表

| 场景 | 图片数 | 主要模型 | 重点文字内容 |
|---|---|---|---|
| 1 食品过期 | 6 | 诚品优选、私信通、实物 | ¥138、十倍赔偿 1380 元 |
| 2 相机虚假宣传 | 7 | 惠购优品、私信通、实物 | ¥14800、假一赔十 |
| 3 家装违约 | 6 | 私信通、合同、实物 | ¥80000、2026-03-01 竣工 |
| 4 外卖苍蝇 | 5 | 即享外卖、私信通、实物 | ¥28、1000 元保底 |
| 5 健身房跑路 | 5 | 私信通、合同、实物 | ¥3000、47 条投诉 |
| 6 商家反证 | 6 | 海淘集市、灵感笔记、合同 | 18 天、质检合格 |
| **合计** | **35** | — | — |

---

> 📌 **最后提醒**：建议把这 35 张 prompt 复制到 Notion / 飞书多维表格里管理，每张对应一个"已生成 / 待生成 / 待校对"状态，方便多人协作完成演示素材。
