#!/usr/bin/env python3
"""
Smoke Test - 测试 LLM API 和 GitHub API 连通性
"""

import asyncio
import sys
import os

# 添加 backend 目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agents.gemini_analyzer import gemini_analyzer
from app.agents.github_agent import github_agent
from app.agents.youtube_agent import youtube_agent


async def test_llm_api():
    """测试 LLM API (Kimi) 连通性"""
    print("\n" + "=" * 60)
    print("测试 LLM API (Kimi)...")
    print("=" * 60)

    if not gemini_analyzer.api_key:
        print("❌ LLM API Key 未配置")
        return False

    print(f"✅ API Key 已配置: {gemini_analyzer.api_key[:10]}...")
    print(f"✅ Base URL: {gemini_analyzer.base_url}")
    print(f"✅ Model: {gemini_analyzer.model_name}")
    print(f"✅ 使用 OpenAI 兼容接口: {gemini_analyzer.use_openai_compatible}")

    # 测试网络连通性
    if not gemini_analyzer.is_available:
        print("❌ LLM API 网络不可达")
        return False
    print("✅ 网络连通性检测通过")

    # 测试实际调用
    print("\n正在测试 LLM API 调用...")
    try:
        result = await gemini_analyzer._generate_content("请用一句话回答：1+1等于几？")
        print(f"✅ LLM API 调用成功！")
        print(f"   响应: {result[:100]}..." if len(result) > 100 else f"   响应: {result}")
        return True
    except Exception as e:
        print(f"❌ LLM API 调用失败: {e}")
        return False


async def test_github_api():
    """测试 GitHub API 连通性"""
    print("\n" + "=" * 60)
    print("测试 GitHub API...")
    print("=" * 60)

    if not github_agent.is_available:
        print("❌ GitHub Token 未配置")
        return False

    print(f"✅ GitHub Token 已配置")

    # 测试实际调用
    print("\n正在测试 GitHub API 调用...")
    try:
        repos = await github_agent.search_trending_repos(
            keywords=["AI agent"],
            days_ago=7,
            min_stars=100
        )
        if repos:
            print(f"✅ GitHub API 调用成功！找到 {len(repos)} 个仓库")
            print(f"   示例: {repos[0].full_name} (⭐{repos[0].stargazers_count})")
            return True
        else:
            print("⚠️ GitHub API 调用成功，但未找到仓库（可能是搜索条件太严格）")
            return True
    except Exception as e:
        print(f"❌ GitHub API 调用失败: {e}")
        return False


async def test_youtube_api():
    """测试 YouTube API 连通性"""
    print("\n" + "=" * 60)
    print("测试 YouTube API...")
    print("=" * 60)

    if not youtube_agent.is_available:
        print("⚠️ YouTube API 未配置或网络不可达（预期行为：国内环境无代理时不可用）")
        return True  # 不阻止后续流程

    print(f"✅ YouTube API Key 已配置")

    # 测试网络连通性
    if not youtube_agent._check_network():
        print("⚠️ YouTube API 网络不可达（预期行为：国内环境无代理时不可用）")
        return True  # 不阻止后续流程

    print("✅ YouTube API 网络连通性检测通过")
    return True


async def test_github_analysis():
    """测试完整的 GitHub 仓库分析流程"""
    print("\n" + "=" * 60)
    print("测试完整 GitHub 分析流程...")
    print("=" * 60)

    if not github_agent.is_available:
        print("❌ GitHub 不可用，跳过完整分析测试")
        return False

    if not gemini_analyzer.is_available:
        print("❌ LLM 不可用，跳过完整分析测试")
        return False

    try:
        # 获取一个仓库
        repos = await github_agent.search_trending_repos(
            keywords=["AI agent"],
            days_ago=7,
            min_stars=100
        )

        if not repos:
            print("⚠️ 未找到仓库进行测试")
            return True

        repo = repos[0]
        print(f"\n分析仓库: {repo.full_name}")
        print(f"描述: {repo.description or '无'}")
        print(f"Stars: {repo.stargazers_count}")

        # 获取详情
        details = await github_agent.fetch_repo_details(repo)
        print(f"README 长度: {len(details.get('readme_content', ''))} 字符")

        # 使用 LLM 分析
        print("\n正在使用 LLM 分析...")
        item = await github_agent.analyze_repo(repo, details)

        print(f"\n✅ 分析完成！")
        print(f"   摘要: {item.summary[:200]}..." if len(item.summary) > 200 else f"   摘要: {item.summary}")
        print(f"   为何热门: {item.why_trending[:100]}..." if item.why_trending and len(item.why_trending) > 100 else f"   为何热门: {item.why_trending}")
        print(f"   创新点: {item.key_innovations[:3]}" if item.key_innovations else "   创新点: 无")

        return True
    except Exception as e:
        print(f"❌ 完整分析测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("Daily AI Digest - Smoke Test")
    print("=" * 60)

    results = {}

    # 测试 LLM API
    results["llm"] = await test_llm_api()

    # 测试 GitHub API
    results["github"] = await test_github_api()

    # 测试 YouTube API
    results["youtube"] = await test_youtube_api()

    # 测试完整分析流程（仅当 LLM 和 GitHub 都可用时）
    if results["llm"] and results["github"]:
        results["full_analysis"] = await test_github_analysis()
    else:
        results["full_analysis"] = False
        print("\n⚠️ 跳过完整分析测试（LLM 或 GitHub 不可用）")

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
        if not passed and name != "youtube":  # YouTube 失败不影响整体
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有核心测试通过！")
        print("=" * 60)
        return 0
    else:
        print("❌ 部分测试失败，请检查配置")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)