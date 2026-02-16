import { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Home, History, Settings } from "lucide-react";

interface LayoutProps {
  children: ReactNode;
}

function Layout({ children }: LayoutProps) {
  const location = useLocation();

  const navItems = [
    { path: "/", label: "首页", icon: Home },
    { path: "/history", label: "历史记录", icon: History },
    { path: "/settings", label: "设置", icon: Settings },
  ];

  return (
    <div className="min-h-screen">
      {/* 顶部：对齐个人站的极简深色风格 */}
      <header className="sticky top-0 z-50 backdrop-blur supports-[backdrop-filter]:bg-neutral-950/70 border-b border-neutral-900">
        <div className="max-w-7xl mx-auto px-6 md:px-16 lg:px-24">
          <div className="h-16 flex items-center justify-between">
            {/* Brand */}
            <Link to="/" className="block">
              <div className="text-xl md:text-2xl font-light tracking-tight text-neutral-50">
                Daily AI Digest
              </div>
              <div className="text-xs text-neutral-500 tracking-widest uppercase">
                Daily Intelligence
              </div>
            </Link>

            {/* Nav */}
            <nav className="flex items-center gap-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={
                      "group inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm transition-all duration-300 " +
                      (isActive
                        ? "bg-neutral-900/60 border border-neutral-800 text-neutral-50"
                        : "text-neutral-400 hover:text-white hover:bg-neutral-900/40")
                    }
                  >
                    <Icon className="w-4 h-4 opacity-80 group-hover:opacity-100" />
                    <span className="font-light">{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>
      </header>

      {/* 主内容区：对齐个人站的左右留白 */}
      <main className="max-w-7xl mx-auto px-6 md:px-16 lg:px-24 py-10 md:py-14">
        {children}
      </main>

      {/* 底部 */}
      <footer className="border-t border-neutral-900 mt-auto">
        <div className="max-w-7xl mx-auto px-6 md:px-16 lg:px-24 py-10">
          <p className="text-neutral-500 text-sm font-light">
            Daily AI Digest © 2024 · 自动追踪 AI 领域最新动态
          </p>
        </div>
      </footer>
    </div>
  );
}

export default Layout;
