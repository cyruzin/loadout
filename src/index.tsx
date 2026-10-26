import {
  ButtonItem,
  ConfirmModal,
  DropdownItem,
  PanelSection,
  PanelSectionRow,
  showModal,
  staticClasses,
  TextField,
} from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { ReactNode, useEffect, useState } from "react";
import { FaSlidersH } from "react-icons/fa";
import * as api from "./api";


const profileLabel = (id: string | null) => api.PROFILES.find((p) => p.id === id)?.label ?? id;

// Cumulative filters: each one also shows what the previous one does.
const FILTERS: { id: api.GameFilter; label: string; keep: (g: api.Game) => boolean }[] = [
  { id: "verified", label: "Verified on this device", keep: (g) => g.verified },
  // Games with a Loadout entry, plus any game Loadout is managing (a profile applied, even generic).
  { id: "loadout", label: "All Loadout games", keep: (g) => g.supported || !!g.profile },
  { id: "all", label: "All games", keep: () => true },
];

// Hundreds of games (installed, or verified once the data grows) make a dropdown nobody can scroll
// with a D-pad: any filter's list is capped to the most recently played ones, plus a search.
const LIST_LIMIT = 50;

function lastPlayed(appid: number): number {
  try {
    return window.appStore?.GetAppOverviewByAppID(appid)?.rt_last_time_played ?? 0;  // Steam internals
  } catch {
    return 0;
  }
}

const GREEN = "#59bf40";
const AMBER = "#e8a33d";

// Short status/warning lines between controls, with room to breathe above and below.
function Notice({ color, children }: { color: string; children: ReactNode }) {
  return <div style={{ fontSize: 12, color, padding: "8px 0" }}>{children}</div>;
}

function gameLabel(g: api.Game) {
  const kind = !g.supported ? " (generic)" : g.verified ? "" : " (untested)";
  return `${g.name}${kind}${g.profile ? ` · ${profileLabel(g.profile)}` : ""}`;
}

// The QAM panel gets remounted (e.g. when a dropdown menu opens), which wipes useState: picks
// made in local state were lost. UI state lives at module level so it survives remounts, and
// every mounted copy re-renders on change (stale closures from a modal still update the UI).
const kept = new Map<string, unknown>();
const subscribers = new Set<() => void>();

function useKept<T>(key: string, initial: T): [T, (value: T) => void] {
  const [, rerender] = useState(0);
  useEffect(() => {
    const notify = () => rerender((n) => n + 1);
    subscribers.add(notify);
    return () => { subscribers.delete(notify); };
  }, []);
  return [(kept.has(key) ? kept.get(key) : initial) as T, (value: T) => setKept(key, value)];
}

function setKept(key: string, value: unknown) {
  kept.set(key, value);
  subscribers.forEach((notify) => notify());
}

type Status = { ok: boolean; text: string };

// Steam may play a toast's sound without showing it (e.g. while the Quick Access Menu is open),
// so every outcome is also written in the panel itself.
function report(ok: boolean, text: string) {
  setKept("status", { ok, text } satisfies Status);
  toaster.toast({ title: "Loadout", body: text, showToast: true });
}

const reportError = (e: unknown) => report(false, String(e));

function describe(plan: api.Plan, running: boolean) {
  const env = plan.changes.filter((c) => c.kind === "env");
  const args = plan.changes.filter((c) => c.kind === "arg");
  const launch = plan.changes.find((c) => c.kind === "launch_option");
  const fileKeys = plan.changes.filter((c) => c.kind === "file_key");
  return (
    <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
      {env.map((c) => <div key={c.key}>{c.key} = {c.new}</div>)}
      {args.map((c) => <div key={c.key}>Game argument: {c.key}</div>)}
      {fileKeys.length > 0 && <div style={{ marginTop: 8 }}>Game settings ({fileKeys[0].target.split("/").pop()}):</div>}
      {fileKeys.map((c) => <div key={c.target + c.key}>{c.key}: {c.old} → {c.new}</div>)}
      {launch ? (
        <>
          <div style={{ marginTop: 8 }}>Launch options before:</div>
          <code>{launch.old || "(empty)"}</code>
          <div style={{ marginTop: 8 }}>After:</div>
          <code>{launch.new || "(empty)"}</code>
        </>
      ) : <div>Nothing to change.</div>}
      {plan.warnings.map((w) => <div key={w} style={{ marginTop: 8, color: "#e8a33d" }}>{w}</div>)}
      {running && <div style={{ marginTop: 8, color: "#e8a33d" }}>Close the game first: it would overwrite its settings on exit.</div>}
      <div style={{ marginTop: 8 }}>Changes apply the next time the game is launched.</div>
    </div>
  );
}

function Onboarding({ boot, onDone }: { boot: api.Bootstrap; onDone: (s: api.Settings) => void }) {
  const [device, setDevice] = useKept("setup.device", boot.detected ?? "generic");
  const detectedName = boot.devices.find((d) => d.id === boot.detected)?.name;
  return (
    <PanelSection title="Setup">
      <PanelSectionRow>
        <div>{detectedName ? `Detected ${detectedName}. Is that right?` : "Device not detected, pick one:"}</div>
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem layout="below" label="Device" rgOptions={boot.devices.map((d) => ({ data: d.id, label: d.name }))}
          selectedOption={device} onChange={(o) => setDevice(o.data)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => api.saveSettings(device).then(onDone, reportError)}>
          Confirm
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

function Content() {
  const [boot, setBoot] = useKept<api.Bootstrap | undefined>("boot", undefined);
  const [settings, setSettings] = useKept<api.Settings | undefined>("settings", undefined);
  const [games, setGames] = useKept<api.Game[]>("games", []);
  const [appid, setAppid] = useKept<number | undefined>("appid", undefined);
  const [busy, setBusy] = useKept("busy", false);
  const [loadError, setLoadError] = useKept<string | undefined>("loadError", undefined);
  const [status] = useKept<Status | undefined>("status", undefined);
  const filter = FILTERS.find((f) => f.id === settings?.game_filter) ?? FILTERS[0];
  const [search, setSearch] = useKept("search", "");
  const inFilter = games.filter(filter.keep);
  // Search only when the list can be capped (a leftover query keeps it visible so it can be cleared).
  const searchable = inFilter.length > LIST_LIMIT || search !== "";
  const query = searchable ? search.trim().toLowerCase() : "";
  const candidates = query ? inFilter.filter((g) => g.name.toLowerCase().includes(query)) : inFilter;
  // Always listed when they match: a game with a profile applied, the running and the picked game.
  const running = window.SteamUIStore?.MainRunningAppID;
  const pinned = (g: api.Game) => !!g.profile || g.appid === appid || g.appid === running;
  const rest = candidates.filter((g) => !pinned(g));
  const cappedOut = Math.max(0, rest.length - LIST_LIMIT);
  const visible = cappedOut  // short lists stay alphabetical; long ones keep the most recently played
    ? [...candidates.filter(pinned), ...rest.sort((a, b) => lastPlayed(b.appid) - lastPlayed(a.appid)).slice(0, LIST_LIMIT)]
    : candidates;
  // Games with a profile applied that the filter hides: listed below, so Default stays reachable.
  const hiddenApplied = games.filter((g) => g.profile && !filter.keep(g));
  // Selection falls back to the first visible game when the current one is hidden.
  const selected = visible.some((g) => g.appid === appid) ? appid : visible[0]?.appid;

  useEffect(() => {
    // A backend that failed to start never answers, so don't wait forever.
    const timer = setTimeout(() => setLoadError("The Loadout backend did not respond."), 10000);
    api.getBootstrap().then(
      async (b) => {
        clearTimeout(timer);
        setBoot(b);
        setSettings(b.settings);
        const g = await api.listGames();
        setGames(g);
        // Which game to show: this session's pick, else the last game configured (survives Steam and
        // Decky restarts), else the running one; `selected` falls back to the first visible game.
        const installed = (id: unknown) => g.some((x) => x.appid === id);
        if (installed(kept.get("appid"))) return;
        const running = window.SteamUIStore?.MainRunningAppID;
        const next = [b.settings.last_game, running].find(installed);
        if (next !== undefined && next !== null) setAppid(next);
      },
      (e) => { clearTimeout(timer); setLoadError(String(e)); },
    ).catch(reportError);
  }, []);

  if (loadError && !boot) {
    return (
      <PanelSection>
        <PanelSectionRow>{loadError} Check the logs in ~/homebrew/logs/Loadout/.</PanelSectionRow>
      </PanelSection>
    );
  }
  if (!boot || !settings) return <PanelSection><PanelSectionRow>Loading…</PanelSectionRow></PanelSection>;
  if (!settings.device) return <Onboarding boot={boot} onDone={setSettings} />;

  const game = selected !== undefined ? settings.games[String(selected)] : undefined;
  const info = games.find((g) => g.appid === selected);
  const current: api.Profile = game?.profile ?? "default";

  const pick = async (profile: api.Profile) => {
    if (selected === undefined || busy) return;
    setBusy(true);
    try {
      const before = await api.getLaunchOptions(selected);
      const plan = await api.planProfile(selected, profile, before);
      // Game config files are never written while the game runs (many games rewrite them on exit).
      const running = plan.file_writes.length > 0 && window.SteamUIStore?.MainRunningAppID === selected;
      showModal(
        <ConfirmModal
          strTitle={`Apply ${api.PROFILES.find((p) => p.id === profile)?.label}?`}
          strDescription={describe(plan, running)}
          bOKDisabled={plan.blocked || running}
          onOK={async () => {
            try {
              // Re-read: the user may have edited launch options while the dialog was open.
              const result = await api.applyProfile(selected, profile, await api.getLaunchOptions(selected));
              if (!result.applied) {
                reportError(result.warnings.join(" "));
                return;
              }
              api.setLaunchOptions(selected, result.launch_options);
              setSettings((await api.getBootstrap()).settings);
              setGames(await api.listGames());  // refresh the applied profile shown next to each game
              report(true, profile === "default"
                ? `${info?.name}: original settings restored.`
                : `${profileLabel(profile)} applied to ${info?.name}. Takes effect the next time it launches.`);
            } catch (e) {
              reportError(e);
            }
          }}
        />,
      );
    } catch (e) {
      reportError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PanelSection title="Game">
        <PanelSectionRow>
          <DropdownItem layout="below" label="Show" rgOptions={FILTERS.map((f) => ({ data: f.id, label: f.label }))}
            selectedOption={filter.id}
            description="Untested: has Loadout settings, not verified on this device. Generic: FPS cap only."
            onChange={(o) => api.setGameFilter(o.data).then(setSettings, reportError)} />
        </PanelSectionRow>
        {searchable && (
          <PanelSectionRow>
            <TextField label="Search games" placeholder="Type part of a name" bShowClearAction
              value={search} onChange={(e) => setSearch(e.target.value)} />
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <DropdownItem layout="below" label="Game" disabled={!visible.length}
            strDefaultLabel={query ? "No games match the search" : "No games for this filter"}
            rgOptions={visible.map((g) => ({ data: g.appid, label: gameLabel(g) }))}
            selectedOption={selected} onChange={(o) => { setAppid(o.data); setKept("status", undefined); }} />
        </PanelSectionRow>
        {cappedOut > 0 && (
          <PanelSectionRow>
            <Notice color={AMBER}>
              {query
                ? `Showing ${LIST_LIMIT} of ${LIST_LIMIT + cappedOut} matches. Type more of the name to narrow it down.`
                : `Lots of games match this filter, so only the ${LIST_LIMIT} most recently played are listed ` +
                  `(${cappedOut} more). Use the search to find any other game.`}
            </Notice>
          </PanelSectionRow>
        )}
        {hiddenApplied.length > 0 && (
          <PanelSectionRow>
            <Notice color={AMBER}>
              Profiles applied to hidden games:{" "}
              {hiddenApplied.map((g) => `${g.name} (${profileLabel(g.profile)})`).join(", ")}.
              Show "All games" to change them.
            </Notice>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <DropdownItem layout="below" label="Profile" disabled={selected === undefined || busy}
            rgOptions={api.PROFILES.map((p) => ({ data: p.id, label: p.label }))}
            selectedOption={current} onChange={(o) => pick(o.data)} />
        </PanelSectionRow>
        {status && (
          <PanelSectionRow>
            <Notice color={status.ok ? GREEN : AMBER}>
              {status.ok ? "✓ " : "⚠ "}{status.text}
            </Notice>
          </PanelSectionRow>
        )}
      </PanelSection>
      <PanelSection title="Settings">
        <PanelSectionRow>
          <DropdownItem layout="below" label="Device" rgOptions={boot.devices.map((d) => ({ data: d.id, label: d.name }))}
            selectedOption={settings.device}
            onChange={(o) => api.saveSettings(o.data).then(setSettings, reportError)} />
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => ({
  name: "Loadout",
  titleView: <div className={staticClasses.Title}>Loadout</div>,
  content: <Content />,
  icon: <FaSlidersH />,
}));
