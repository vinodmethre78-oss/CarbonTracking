import { NavLink, useNavigate } from "react-router-dom";
import { Leaf, LogOut, Menu, X, WifiOff, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import useOnlineStatus from "../hooks/useOnlineStatus";
import ChatAssistant from "./ChatAssistant";
import LanguageSelector from "./LanguageSelector";
import NotificationBell from "./NotificationBell";
import Toaster from "./Toaster";
import CriticalAlertModal from "./CriticalAlertModal";
import IsoTruckBadge from "./IsoTruckBadge";
import api from "../lib/api";

// Desktop sidebar width when expanded (md:w-64, 16rem) vs collapsed
// icon-only rail (md:w-[4.5rem], 72px). The sidebar's width classes and the
// main content's margin-left classes below must always match these two
// values so the content never overlaps or leaves a gap.

export default function DashboardLayout({ nav, children, title }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false); // mobile drawer open/closed
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("sidebarCollapsed") === "1";
    } catch {
      return false;
    }
  }); // desktop expanded/collapsed
  const [unreadCount, setUnreadCount] = useState(0);
  const isOnline = useOnlineStatus();
  const { t } = useTranslation();

  useEffect(() => {
    async function fetchUnread() {
      if (!user) return;
      try {
        const endpoint = user.role === "admin"
          ? "/admin/conversations/unread-count"
          : "/driver/conversations/unread-count";
        const res = await api.get(endpoint);
        setUnreadCount(res.data.unread);
      } catch (err) {
        console.error("Failed to fetch unread count", err);
      }
    }
    fetchUnread();
    const interval = setInterval(fetchUnread, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, [user]);

  // Mobile drawer behaviour: while it is open, (1) lock background scrolling,
  // (2) let Escape close it, and (3) auto-close it if the viewport grows to
  // the desktop breakpoint (rotate / resize) so a stale lock can never
  // survive on a layout that has no drawer. `html` is the scroll container
  // here (index.css sets overflow-y on html), so the lock must be applied to
  // documentElement as well as body; the previous inline values are restored
  // exactly on close/unmount so nothing else's overflow setting is clobbered.
  useEffect(() => {
    if (!open) return;
    const html = document.documentElement;
    const body = document.body;
    const prevHtmlOverflow = html.style.overflow;
    const prevBodyOverflow = body.style.overflow;
    html.style.overflow = "hidden";
    body.style.overflow = "hidden";

    function onKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }
    const mq = window.matchMedia("(min-width: 768px)");
    function onBreakpointChange(e) {
      if (e.matches) setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    mq.addEventListener("change", onBreakpointChange);

    return () => {
      html.style.overflow = prevHtmlOverflow;
      body.style.overflow = prevBodyOverflow;
      window.removeEventListener("keydown", onKeyDown);
      mq.removeEventListener("change", onBreakpointChange);
    };
  }, [open]);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("sidebarCollapsed", next ? "1" : "0");
      } catch {
        // ignore storage errors (private browsing, etc.)
      }
      return next;
    });
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="flex min-h-screen">
      {!isOnline && (
        <div className="fixed inset-x-0 top-0 z-[var(--z-header)] flex items-center justify-center gap-2 bg-amber pb-1.5 pt-[calc(0.375rem+env(safe-area-inset-top,0px))] text-xs font-medium text-black md:pt-1.5">
          <WifiOff size={13} /> {t("offline.message")}
        </div>
      )}
      {/* Mobile top bar */}
      <div className={`glass-strong mobile-topbar trip-console-trim fixed inset-x-0 z-[var(--z-header)] flex items-center justify-between px-4 pb-3 pt-[calc(0.75rem+env(safe-area-inset-top,0px))] md:hidden ${isOnline ? "top-0" : "top-[calc(1.75rem+env(safe-area-inset-top,0px))]"}`}>
        <span className="flex items-center gap-2 font-display text-sm font-semibold text-ink">
          <span className="glow-chip-cyan flex h-7 w-7 items-center justify-center rounded-lg text-success"><Leaf size={14} /></span>
          Carbon<span className="text-amber">Track</span>
        </span>
        <div className="flex items-center gap-1">
          <NotificationBell />
          <LanguageSelector variant="topbar" />
          <button
            onClick={() => setOpen(!open)}
            aria-label={open ? t("common.closeMenu", "Close menu") : t("common.openMenu", "Open menu")}
            aria-expanded={open}
            aria-controls="mobile-nav-drawer"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-ink-dim hover:text-ink"
          >{open ? <X size={20} /> : <Menu size={20} />}</button>
        </div>
      </div>

      {/* Mobile backdrop. Layering on phones, bottom to top:
          page content -> this dark scrim (z-drawer-backdrop) -> drawer
          (z-drawer) -> top bar (z-header, so the X stays tappable).
          Tapping the scrim closes the drawer. Never rendered at md+. */}
      <div
        aria-hidden="true"
        onClick={() => setOpen(false)}
        className={`fixed inset-0 z-[var(--z-drawer-backdrop)] touch-none overscroll-contain bg-black/70 backdrop-blur-sm transition-opacity duration-300 md:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
      />

      {/* Sidebar (desktop) / navigation drawer (mobile). On mobile .sidebar-drawer
          makes the glass near-opaque so the dashboard can't be read through it;
          max-md:invisible (when closed) removes the off-screen drawer from tab
          order/screen readers once its slide-out transition has finished. */}
      <aside
        id="mobile-nav-drawer"
        className={`sidebar-drawer glass-strong trip-console-trim fixed left-0 top-0 bottom-0 z-[var(--z-sidebar)] max-md:z-[var(--z-drawer)] flex h-dvh w-64 shrink-0 flex-col transition-[transform,width,visibility] duration-300 ease-out md:h-screen md:translate-x-0
        ${open ? "translate-x-0" : "-translate-x-full max-md:invisible"} ${collapsed ? "md:w-[4.5rem]" : "md:w-64"} ${isOnline ? "pt-[calc(4rem+env(safe-area-inset-top,0px))] md:pt-0" : "pt-[calc(6rem+env(safe-area-inset-top,0px))] md:pt-7"}`}
      >
        <div className={`hidden items-center gap-2 px-6 py-6 md:flex ${collapsed ? "md:justify-center md:px-0" : "md:justify-between"}`}>
          <div className="flex items-center gap-2 overflow-hidden">
            <span className="glow-chip-cyan flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-success"><Leaf size={16} /></span>
            <span className={`font-display text-lg font-semibold whitespace-nowrap text-ink transition-all duration-200 ${collapsed ? "md:w-0 md:opacity-0" : "md:w-auto md:opacity-100"}`}>
              Carbon<span className="text-amber">Track</span>
            </span>
          </div>
          {!collapsed && (
            <button
              onClick={toggleCollapsed}
              aria-label={t("common.collapseSidebar", "Collapse sidebar")}
              className="hidden shrink-0 rounded-lg p-1.5 text-ink-dim hover:bg-white/[0.06] hover:text-ink md:flex"
            >
              <PanelLeftClose size={17} />
            </button>
          )}
        </div>
        {collapsed && (
          <button
            onClick={toggleCollapsed}
            aria-label={t("common.expandSidebar", "Expand sidebar")}
            className="mx-auto mb-2 hidden rounded-lg p-1.5 text-ink-dim hover:bg-white/[0.06] hover:text-ink md:flex"
          >
            <PanelLeftOpen size={17} />
          </button>
        )}

        <nav className="sidebar-scroll mt-2 flex min-h-0 flex-1 flex-col gap-1 overflow-x-hidden overflow-y-auto overscroll-contain scroll-smooth px-3">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setOpen(false)}
              title={collapsed ? t(item.labelKey) : undefined}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors
                ${collapsed ? "md:justify-center md:px-2" : ""}
                ${isActive ? "bg-indigo/15 text-cyan-soft shadow-[inset_0_0_0_1px_rgba(34,211,238,0.25)]" : "text-ink-dim hover:bg-white/[0.04] hover:text-ink"}`
              }
            >
              <div className="relative">
                <item.icon size={17} className="shrink-0" />
                { (item.to === "/admin/conversations" || item.to === "/driver/conversations") && unreadCount > 0 && (
                  <span className="absolute -right-1 -top-1 flex h-3 w-3 items-center justify-center rounded-full bg-amber text-[8px] font-bold text-black shadow-sm">
                    {unreadCount > 9 ? "9+" : unreadCount}
                  </span>
                )}
              </div>
              <span className={collapsed ? "md:hidden" : ""}>{t(item.labelKey)}</span>
            </NavLink>
          ))}
        </nav>

        <div className="w-full border-t border-white/5 p-4 max-md:pb-[calc(1rem+env(safe-area-inset-bottom,0px))]">
          <div className={`mb-3 rounded-xl bg-white/[0.03] px-3 py-2.5 ${collapsed ? "md:hidden" : ""}`}>
            <p className="truncate text-sm font-medium text-ink">{user?.name}</p>
            <p className="text-xs text-ink-dim">{user?.username}</p>
          </div>
          <div className={`mb-1 ${collapsed ? "md:hidden" : ""}`}>
            <LanguageSelector variant="sidebar" />
          </div>
          <button
            onClick={handleLogout}
            title={collapsed ? t("nav.logout") : undefined}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-ink-dim hover:bg-danger/10 hover:text-danger ${collapsed ? "md:justify-center md:px-2" : ""}`}
          >
            <LogOut size={16} className="shrink-0" /> <span className={collapsed ? "md:hidden" : ""}>{t("nav.logout")}</span>
          </button>
        </div>
      </aside>

      {/* Content */}
      <main className={`ml-0 flex-1 px-5 pb-16 pt-[calc(5.5rem+env(safe-area-inset-top,0px))] transition-[margin] duration-300 ease-out md:px-8 md:pt-8 ${collapsed ? "md:ml-[4.5rem]" : "md:ml-64"}`}>
        {title ? (
          <div className="trip-console-trim glass mb-6 flex items-center justify-between gap-3 rounded-2xl px-5 py-4">
            <div className="flex items-center gap-3">
              <span className="glow-chip-cyan flex h-9 w-9 shrink-0 items-center justify-center rounded-xl">
                <IsoTruckBadge size={20} />
              </span>
              <h1 className="font-display text-xl font-semibold text-ink md:text-2xl">{title}</h1>
            </div>
            <span className="hidden md:inline"><NotificationBell /></span>
          </div>
        ) : (
          <div className="mb-6 hidden items-center justify-end md:flex"><NotificationBell /></div>
        )}
        {children}
      </main>

      <Toaster />
      <CriticalAlertModal />
      {/* The floating AI button/panel is z-90, above the drawer; hide it on
          mobile while the drawer is open (stays mounted, so chat state is kept). */}
      <div className={open ? "max-md:hidden" : undefined}>
        <ChatAssistant />
      </div>
    </div>
  );
}