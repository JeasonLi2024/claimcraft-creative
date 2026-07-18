# 前端静态资源加载性能优化方案

> 文档状态：优化方案（待实施）
> 适用范围：服务器部署环境下 logo、背景图、字体等静态资源加载慢的问题
> 部署形态：`Dockerfile.frontend`（`vite build` → `nginx:alpine`，`dist` 复制到 `/usr/share/nginx/html`，`nginx.conf` 复制到 `/etc/nginx/conf.d/default.conf`）
> 结论日期：2026-07-19

---

## 1. 问题现象

服务器访问页面时，静态内容（logo、首页背景图、字体等）加载明显偏慢，首屏体验受影响。

## 2. 诊断结论

**根因是「静态资源体积过大」叠加「nginx 未启用压缩与缓存」，与业务逻辑无关。**

### 2.1 静态资源体积清单（`frontend/public/`）

| 资源 | 体积 | 用途 / 问题 |
|---|---|---|
| `首页 Hero 背景.png` | **11 MB** | 首页 Hero 背景，实际以 `opacity:0.2` 作装饰，分辨率与体积严重过剩 |
| `得意黑.zip` | **6.0 MB** | 字体**源码 zip 被放入 public/**，随镜像分发；页面并不加载，纯属死重量 |
| `阿里妈妈灵动体（alimama agile）.zip` | 192 KB | 同上，字体源码 zip 不应进 public/ |
| `logo.jpg` | **2.0 MB** | logo 用 2MB 位图，应为 SVG 或极小 PNG |
| `登录页视觉图.png` | 1.5 MB | 登录页装饰图，未压缩 |
| `fonts/deyihei/SmileySans-Oblique.woff2` | 1.3 MB | 整套中文字体，未按实际用到的字形子集化 |
| `空状态插画.png` | 928 KB | 设计仅展示 160–240px，却近 1MB |
| `fonts/alimama-agile/AlimamaAgileVF-Thin.woff2` | 60 KB | 拉丁字体，可接受 |
| `favicon.svg` / `icons.svg` | 4 KB / 8 KB | 正常 |

**首屏关键路径粗估**：Hero(11M) + logo(2M) + 中文字体(1.3M) + 打包 JS/CSS ≈ **15 MB 量级**；登录页另含 1.5M 视觉图。

### 2.2 nginx 侧放大因素（`nginx.conf`）

当前 `nginx.conf` 为 `server` 块，通过 `Dockerfile.frontend` 复制到 `conf.d/default.conf`；`nginx:alpine` 默认 `http{}` 的 `gzip` 处于关闭状态。存在三个问题：

1. **未启用 gzip / brotli**：JS、CSS、SVG 明文传输（Vite 构建报告的 `gzip 114KB` 并未在传输层生效）。
2. **无缓存头**：`location /` 未设置 `expires` / `Cache-Control`。带内容哈希、本可永久缓存的 `/assets/*.js|css` 每次访问都重新下载；logo、背景、字体同样不被浏览器复用，二次访问依旧慢。
3. **仅 `listen 80`、无 HTTP/2**：大量小文件串行请求，握手与排队开销叠加。

### 2.3 其它

- 资源使用中文文件名（`首页 Hero 背景.png` 等），请求时 URL 编码，可读性与部分中间层缓存友好度略差（非主因）。
- 字体已使用 `unicode-range` 拆分 + `font-display: swap`（良好：正文先用回退字体渲染，不阻塞首屏），但 1.3MB 的 CJK 字体仍会在含中文时被拉取。

---

## 3. 优化方案（按收益 / 成本排序）

### P0 · 压缩大图（收益最大，纯资源处理，零配置风险）

目标：把首屏图片从 ~15MB 降到 **< 0.5MB**。

| 资源 | 处理动作 | 目标 |
|---|---|---|
| `首页 Hero 背景.png` | 降分辨率（≤1920px 宽）+ 转 WebP/AVIF | ~100–300 KB（约 40–100× 缩减） |
| `logo.jpg` | 改用 SVG（已有 `favicon.svg` 可参考）或 ≤256px PNG | ≤ 20 KB |
| `登录页视觉图.png` | 按实际显示尺寸 + 转 WebP | ~100–200 KB |
| `空状态插画.png` | 按 160–240px 导出 + 转 WebP，或改用设计稿建议的 SVG | 几 KB |

参考命令（离线处理，人工确认可接受有损压缩与目标分辨率后执行）：

```bash
# WebP（有损，q80 通常肉眼无损且体积大幅下降）
cwebp -q 80 "首页 Hero 背景.png" -o hero-bg.webp
cwebp -q 80 "登录页视觉图.png" -o auth-visual.webp
cwebp -q 82 "空状态插画.png" -o empty-state.webp

# 或用 ImageMagick 先缩放再转
magick "首页 Hero 背景.png" -resize 1920x hero-bg.webp
magick logo.jpg -resize 256x -strip logo.png
```

注意：引用处（`HomePage.tsx` / `AuthShell.tsx` / `EmptyState.tsx` / `CaseListPage.tsx` / `index.css`）需同步更新为新文件名/格式，属代码改动，纳入实施阶段。可保留 `<picture>` 提供 WebP + PNG 回退以兼容极老浏览器（现代浏览器均支持 WebP，通常可直接替换）。

### P1 · nginx 启用压缩 + 强缓存（+ HTTP/2）（配置改动）

在 `nginx.conf` 的 `server` 块内补充：

```nginx
# 文本类资源压缩（woff2/png/jpg/webp 已是压缩格式，不重复 gzip）
gzip on;
gzip_comp_level 5;
gzip_min_length 1024;
gzip_vary on;
gzip_types text/plain text/css application/javascript application/json image/svg+xml;

# Vite 带内容哈希的构建产物：可安全永久缓存
location /assets/ {
    root /usr/share/nginx/html;
    expires 1y;
    add_header Cache-Control "public, immutable";
    try_files $uri =404;
}

# 命名的 public 静态资源（logo/背景/插画/字体）：中长期缓存
location ~* \.(?:woff2|ttf|otf|png|jpe?g|webp|avif|svg|ico)$ {
    root /usr/share/nginx/html;
    expires 30d;
    add_header Cache-Control "public";
    try_files $uri =404;
}
```

补充建议：
- **HTTP/2**：若入口未由上层 LB 终止 TLS，则在本层启用 `listen 443 ssl http2;`（需证书）。HTTP/2 多路复用显著改善"多小文件"场景。
- **brotli**：若 nginx 编译了 `ngx_brotli`，对文本资源比 gzip 更省，可一并启用。
- 现有 SSE 端点 `gzip off` 的设置**保持不动**（流式必须关压缩缓冲）。

### P2 · 从 public/ 移除字体源码 zip（立减 ~6.2MB 镜像/部署体积）

`frontend/public/得意黑.zip`、`frontend/public/阿里妈妈灵动体（alimama agile）.zip` 会被 `COPY --from=build /app/dist` 打进 nginx 镜像。它们不是运行期资源，应移出 `public/`（迁到仓库外或 `docs/assets/`、`.gitignore` 忽略），镜像与部署体积立减约 6MB。

### P3 · 字体子集化（1.3MB CJK → 100–300KB）

- 现状：`SmileySans-Oblique.woff2` 是完整中文字体，`unicode-range` 已限制仅 CJK 时加载，`font-display: swap` 已避免阻塞。
- 优化：用 `fonttools` / `glyphhanger` 按项目实际使用到的汉字做**子集化**，通常可从 1.3MB 降到 100–300KB。
  ```bash
  # 示例：pyftsubset 按字符集裁剪（--text-file 收集项目中出现的汉字）
  pyftsubset SmileySans-Oblique.woff2 --unicodes-file=used-cjk.txt \
    --flavor=woff2 --output-file=SmileySans-subset.woff2
  ```
- 对首屏主字体可加预加载减少字体切换抖动（FOUT）：
  ```html
  <link rel="preload" href="/fonts/deyihei/SmileySans-subset.woff2" as="font" type="font/woff2" crossorigin>
  ```

### P4 · 交付细节（长期）

- 非首屏图片（如列表页空状态、登录视觉图若不在首屏）加 `loading="lazy"`。
- `<link rel="preconnect">` / `dns-prefetch` 到后端与字体来源域。
- 静态资源与 API 分域，接入 **CDN / 对象存储** 托管 `public` 大资源，减轻源站带宽。
- 可选：构建期集成图片压缩（如 `vite-plugin-imagemin`），避免大图再次混入。

---

## 4. 实施顺序建议

1. **P0（压图）+ P2（删 zip）**：一次即可把首屏从十几 MB 降到 <1MB，收益最直接；P2 不碰业务代码，P0 仅改资源与引用路径。
2. **P1（nginx gzip + 缓存 + HTTP/2）**：解决"JS/CSS 明文传输"与"二次访问仍慢"。
3. **P3（字体子集化）**：再压掉 1MB+ 并稳定首屏字体。
4. **P4**：按需长期推进。

---

## 5. 验收指标

- **首屏传输量**：Home / 登录页首次加载资源总量从 ~15MB 降到 **< 1.5MB**。
- **单资源体积**：Hero < 300KB、logo < 20KB、空状态 < 20KB、CJK 字体 < 300KB。
- **压缩生效**：DevTools Network 中 JS/CSS 响应头含 `Content-Encoding: gzip`（或 br）。
- **缓存生效**：`/assets/*` 响应头含 `Cache-Control: public, immutable`；二次访问命中磁盘/内存缓存（Status 200 (from cache)）。
- **镜像体积**：前端镜像减少约 6MB（移除 zip 后）。
- **主观**：Lighthouse Performance 提升，LCP 明显下降。

## 6. 验证方法

```bash
# 压缩是否生效
curl -s -H "Accept-Encoding: gzip" -I https://<host>/assets/<hashed>.js | grep -i content-encoding
# 缓存头是否生效
curl -s -I https://<host>/logo.png | grep -i cache-control
# 单资源体积
curl -s -o /dev/null -w "%{size_download}\n" https://<host>/hero-bg.webp
```
配合浏览器 DevTools → Network（勾选 Disable cache 看首次，取消勾选看二次复用）与 Lighthouse 前后对比。

---

## 7. 风险与注意

- **P0 图片有损压缩**：需产品/设计确认可接受的画质与目标分辨率；建议保留原图备份，装饰性背景可较激进压缩。
- **P0 引用路径改动**：更换文件名/格式后需同步更新前端引用（`HomePage`/`AuthShell`/`EmptyState`/`CaseListPage`/`index.css`），并回归首页、登录页、案件列表空状态、字体渲染。
- **P1 缓存策略**：永久缓存只对**带内容哈希**的 `/assets/*` 安全；命名资源（logo 等）用 30d 即可，避免更新后长期不生效。若担心更新延迟，可对命名资源改文件名或加版本查询参数。
- **P1 不影响 SSE**：保持工作流流式端点 `gzip off` 与 `proxy_buffering off` 不变。
- **中文文件名**：借 P0 重导出时可顺带改为英文短名（如 `hero-bg.webp`），提升可维护性；同样属引用改动。
