# BOSS 直聘岗位抓取脚本

这个脚本会按关键词打开 BOSS 直聘搜索页，并读取页面上可见的前 10 个岗位信息。

## 安装

```powershell
pip install -r requirements.txt
playwright install chromium
```

## 使用

```powershell
python boss_zhipin_scraper.py 数据分析
```

默认抓取“全国”的前 10 条，并保存到 `boss_jobs.csv`。

也可以指定城市和输出文件：

```powershell
python boss_zhipin_scraper.py BI --city 上海 --output boss_jobs.json
```

如果网页出现登录、滑块或验证码，请在打开的浏览器中先手动完成。脚本不会绕过网站验证，只读取你能正常看到的岗位信息。
