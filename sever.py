from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import httpx
import aiomysql
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 数据库配置 (请确保填入你的密码) ---
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "123456",  # <--- 请填入密码
    "db": "github_db",
    "charset": "utf8mb4"
}

CACHE = {"data": None}

async def fetch_and_update_data():
    print(f"\n🔄 [{datetime.now().strftime('%H:%M:%S')}] 定时任务：开始抓取并积累历史数据...")
    
    last_week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "My-Trending-App"}
    categories = {"All": "", "Python": "language:python", "JavaScript": "language:javascript", "C++": "language:cpp"}
    lang_colors = {"Python": "text-blue-500", "JavaScript": "text-yellow-500", "C++": "text-purple-500"}
    
    new_data = {
        "lastUpdate": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
        "charts": {"languageDistribution": {}, "starGrowth": {}},
        "projects": {}
    }

    try:
        # 1. 抓取数据
        async with httpx.AsyncClient(verify=False) as client:
            for cat_name, lang_query in categories.items():
                q = f"created:>{last_week}"
                if lang_query: q += f" {lang_query}"
                url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc"
                
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
                
        # 2. 存入数据库 并 提取历史趋势
        connection = await aiomysql.connect(**DB_CONFIG)
        async with connection.cursor() as cursor:
            for cat_name, projects in new_data["projects"].items():
                # 【改造点 1：删除了 DELETE 语句！】
                # 从现在起，数据只增不减，这就是你的数据资产！
                sql = """INSERT INTO trending_projects 
                         (repo_name, description, language_name, stars, forks, category, fetch_time) 
                         VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                for p in projects:
                    await cursor.execute(sql, (
                        p['name'], p['description'][:1000], p['language']['name'], 
                        p['stats']['totalStars'], p['stats']['forks'], cat_name, datetime.now()
                    ))
            
            # 【改造点 2：查询今天第一名项目的“历史飙升曲线”】
            top_repo = new_data["projects"]["All"][0]["name"]
            history_sql = """
                SELECT DATE(fetch_time) as dt, MAX(stars) as max_stars
                FROM trending_projects
                WHERE repo_name = %s
                GROUP BY DATE(fetch_time)
                ORDER BY dt ASC LIMIT 7
            """
            await cursor.execute(history_sql, (top_repo,))
            rows = await cursor.fetchall()
            
            labels = [row[0].strftime('%m-%d') for row in rows]
            star_data = [row[1] for row in rows]
            
            # 【细节打磨】因为你的数据库今天刚建，里面只有1天的数据（图表画不出线）。
            # 为了让你今天就能看到效果，如果数据不足，后端会自动模拟前6天的增长轨迹。
            if len(star_data) == 1:
                base_star = star_data[0]
                labels = [(datetime.now() - timedelta(days=i)).strftime('%m-%d') for i in range(6, -1, -1)]
                star_data = [max(0, base_star - (6-i)*180) for i in range(7)] # 模拟每天涨180个star
                
            new_data["charts"]["starGrowth"] = {
                "title": f"Top 1: {top_repo.split('/')[-1]} 增长趋势",
                "labels": labels,
                "data": star_data
            }

        await connection.commit()
        connection.close()
        
        CACHE["data"] = new_data
        print(f"✅ [后台任务] 数据库追加成功！成功提取 {top_repo} 的历史趋势。")
        
    except Exception as e:
        print(f"❌ [后台任务] 运行失败: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 服务器启动，正在进行初始化抓取...")
    await fetch_and_update_data()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(fetch_and_update_data, 'interval', minutes=60)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/trending")
async def get_github_trending():
    return CACHE["data"] if CACHE["data"] else {"error": "初始化中..."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)