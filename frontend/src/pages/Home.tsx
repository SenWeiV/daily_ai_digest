import { useState, useEffect } from "react";
import { RefreshCw, Calendar } from "lucide-react";
import Dashboard from "../components/Dashboard";
import GitHubList from "../components/GitHubList";
import ArxivList from "../components/ArxivList";
import YouTubeList from "../components/YouTubeList";
import DetailModal from "../components/DetailModal";
import { digestApi, systemApi } from "../services/api";
import type {
  DigestRecord,
  SystemStatus,
  GitHubDigestItem,
  YouTubeDigestItem,
} from "../types";

// 摘要类型选项
const DIGEST_TYPE_OPTIONS = [
  { value: "daily", label: "每日", description: "今日热点" },
  { value: "weekly", label: "每周", description: "本周精选" },
  { value: "monthly", label: "每月", description: "本月热门" },
] as const;

type DigestType = "daily" | "weekly" | "monthly";

function Home() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [digest, setDigest] = useState<DigestRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [selectedItem, setSelectedItem] = useState<
    GitHubDigestItem | YouTubeDigestItem | null
  >(null);
  const [selectedType, setSelectedType] = useState<"github" | "youtube">(
    "github",
  );
  const [activeTab, setActiveTab] = useState<"github" | "arxiv" | "youtube">("github");
  const [digestType, setDigestType] = useState<DigestType>("daily");

  // 加载数据
  const loadData = async () => {
    try {
      setLoading(true);
      const [statusData, digestData] = await Promise.all([
        systemApi.getStatus(),
        digestApi.getLatest(),
      ]);
      setStatus(statusData);
      setDigest(digestData);
    } catch (error) {
      console.error("加载数据失败:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // 手动触发
  const handleTrigger = async () => {
    if (triggering) return;

    try {
      setTriggering(true);
      const response = await digestApi.trigger({
        force: false,
        send_email: true,
        digest_type: digestType,
      });
      if (response.success) {
        const typeLabel = DIGEST_TYPE_OPTIONS.find(o => o.value === digestType)?.label || "";
        alert(`${typeLabel}摘要生成任务已启动，请稍后刷新查看结果`);
      } else {
        alert(response.message);
      }
    } catch (error) {
      console.error("触发失败:", error);
      alert("触发失败，请检查配置");
    } finally {
      setTriggering(false);
    }
  };

  // 点击项目详情
  const handleGitHubClick = (item: GitHubDigestItem) => {
    setSelectedItem(item);
    setSelectedType("github");
  };

  const handleYouTubeClick = (item: YouTubeDigestItem) => {
    setSelectedItem(item);
    setSelectedType("youtube");
  };

  return (
    <div>
      {/* 页面标题 */}
      <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between mb-10">
        <div>
          <h1 className="text-4xl md:text-5xl font-light tracking-tight text-neutral-50">
            Digest
          </h1>
          <p className="mt-4 text-neutral-400 max-w-xl font-light">
            {digest?.digest_date
              ? `${digest.digest_date} 的 AI 热点情报`
              : "暂无数据"}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {/* 摘要类型选择器 */}
          <div className="flex gap-1 bg-neutral-900/40 border border-neutral-800 rounded-full p-1">
            {DIGEST_TYPE_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => setDigestType(option.value)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  digestType === option.value
                    ? "bg-violet-600 text-white"
                    : "text-neutral-400 hover:text-white"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <button
            onClick={loadData}
            className="inline-flex items-center px-4 py-2 rounded-full border border-neutral-800 text-neutral-200 hover:bg-neutral-900/40 transition-colors"
          >
            <RefreshCw
              className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`}
            />
            刷新
          </button>
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="inline-flex items-center px-5 py-2 rounded-full bg-neutral-50 text-neutral-950 hover:bg-white transition-colors disabled:opacity-50"
          >
            <Calendar
              className={`w-4 h-4 mr-2 ${triggering ? "animate-spin" : ""}`}
            />
            {triggering ? "生成中..." : `生成${DIGEST_TYPE_OPTIONS.find(o => o.value === digestType)?.label || ""}摘要`}
          </button>
        </div>
      </div>

      {/* 统计卡片 */}
      <Dashboard status={status} digest={digest} loading={loading} />

      {/* Tab 切换 */}
      <div className="flex gap-1 mb-8 bg-neutral-900/40 border border-neutral-800 rounded-full p-1 w-fit">
        <button
          onClick={() => setActiveTab("github")}
          className={`px-6 py-2 rounded-md font-medium transition-colors ${
            activeTab === "github"
              ? "bg-neutral-950 text-neutral-50 border border-neutral-800 rounded-full"
              : "text-neutral-400 hover:text-white rounded-full"
          }`}
        >
          🐙 GitHub Top {digest?.github_data?.length || 0}
        </button>
        <button
          onClick={() => setActiveTab("arxiv")}
          className={`px-6 py-2 rounded-md font-medium transition-colors ${
            activeTab === "arxiv"
              ? "bg-neutral-950 text-neutral-50 border border-neutral-800 rounded-full"
              : "text-neutral-400 hover:text-white rounded-full"
          }`}
        >
          📄 arXiv {digest?.arxiv_data?.length || 0}
        </button>
        <button
          onClick={() => setActiveTab("youtube")}
          className={`px-6 py-2 rounded-md font-medium transition-colors ${
            activeTab === "youtube"
              ? "bg-neutral-950 text-neutral-50 border border-neutral-800 rounded-full"
              : "text-neutral-400 hover:text-white rounded-full"
          }`}
        >
          📺 YouTube Top {digest?.youtube_data?.length || 0}
        </button>
      </div>

      {/* 内容列表 */}
      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="surface rounded-2xl p-6 animate-pulse">
              <div className="h-6 bg-neutral-800 rounded w-1/3 mb-4"></div>
              <div className="h-4 bg-neutral-800 rounded w-2/3 mb-2"></div>
              <div className="h-4 bg-neutral-800 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      ) : (
        <>
          {activeTab === "github" ? (
            <GitHubList
              items={digest?.github_data || []}
              onItemClick={handleGitHubClick}
            />
          ) : activeTab === "arxiv" ? (
            <ArxivList items={digest?.arxiv_data || []} />
          ) : (
            <YouTubeList
              items={digest?.youtube_data || []}
              onItemClick={handleYouTubeClick}
            />
          )}
        </>
      )}

      {/* 详情弹窗 */}
      <DetailModal
        item={selectedItem}
        type={selectedType}
        onClose={() => setSelectedItem(null)}
      />
    </div>
  );
}

export default Home;
