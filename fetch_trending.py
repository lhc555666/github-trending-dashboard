import httpx
import asyncio
import json
from datetime import datetime, timedelta

async def fetch_data():
    print(f"🚀 开始抓取 GitHub 数据...")
    last_week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "GitHub-Actions-Bot"}
    categories = {"All": "", "Python": "language:python", "JavaScript": "language:javascript", "C++": "language:cpp"}
    lang_colors = {"Python": "text-blue-500", "JavaScript": "text-yellow-500", "C++": "text-purple-500"}
    
    new_data = {
        "lastUpdate": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
        "charts": {"languageDistribution": {}, "starGrowth": {}},
        "projects": {}
    }

    async with httpx.AsyncClient(verify=False) as client:
        for cat_name, lang_query in categories.items():
            q = f"created:>{last_week}"
            if lang_query: q += f" {lang_query}"
            url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc"
            
            try:
                res = await client.get(url, headers=headers, timeout=15.0)
                items = res.json().get("items", [])
                
                project_list = []
                for index, item in enumerate(items[:10], 1):
                    lang = item.get('language') or 'Unknown'
                    p = {
                        "rank": index, "name": item.get('full_name'),
                        "description": item.get('description') or '暂无描述',
                        "language": {"name": lang, "color": lang_colors.get(lang, "text-gray-500")},
                        "stats": {"todayStars": "-", "totalStars": item.get('stargazers_count'), "forks": item.get('forks_count')},
                        "contributors": [item.get('owner', {}).get('avatar_url')],
                        "tags": [f"#{lang}".replace("#Unknown", "#Trending")]
                    }
                    project_list.append(p)
                    if cat_name == "All" and lang != "Unknown":
                        new_data["charts"]["languageDistribution"][lang] = new_data["charts"]["languageDistribution"].get(lang, 0) + 1
                
                new_data["projects"][cat_name] = project_list
            except Exception as e:
                print(f"❌ 抓取 {cat_name} 失败: {e}")

    # 将数据写入同级目录的 data.json
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    print("✅ 数据已成功写入 data.json")

if __name__ == "__main__":
    asyncio.run(fetch_data())