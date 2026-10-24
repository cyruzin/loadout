import {
  ButtonItem,
  ConfirmModal,
  DropdownItem,
  PanelSection,
  PanelSectionRow,
  showModal,
  staticClasses,
} from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaSlidersH } from "react-icons/fa";
import * as api from "./api";

const errorToast = (e: unknown) => toaster.toast({ title: "Loadout", body: String(e) });

const profileLabel = (id: string | null) => api.PROFILES.find((p) => p.id === id)?.label ?? id;

// Cumulative filters: each one also shows what the previous one does.
const FILTERS: { id: api.GameFilter; label: string; keep: (g: api.Game) => boolean }[] = [
  { id: "verified", label: "Verified on this device", keep: (g) => g.verified },
  { id: "loadout", label: "All Loadout games", keep: (g) => g.supported },
  { id: "all", label: "All games", keep: () => true },
];

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
  const set = (value: T) => {
    kept.set(key, value);
    subscribers.forEach((notify) => notify());
  };
  return [(kept.has(key) ? kept.get(key) : initial) as T, set];
}

function describe(plan: api.Plan, running: boolean) {
  const env = plan.changes.filter((c) => c.kind === "env");
  const launch = plan.changes.find((c) => c.kind === "launch_option");
  const fileKeys = plan.changes.filter((c) => c.kind === "file_key");
  return (
    <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
      {env.map((c) => <div key={c.key}>{c.key} = {c.new}</div>)}
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
  const native = boot.devices.find((d) => d.id === device)?.native ?? "1080p";
  const [res, setRes] = useKept<string | null>("setup.resolution", null);
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
        <DropdownItem layout="below" label="Render resolution" rgOptions={boot.resolutions.map((r) => ({ data: r, label: r }))}
          selectedOption={res ?? native} onChange={(o) => setRes(o.data)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => api.saveSettings(device, res ?? native).then(onDone, errorToast)}>
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
  const filter = FILTERS.find((f) => f.id === settings?.game_filter) ?? FILTERS[0];
  const visible = games.filter(filter.keep);
  // Games with a profile applied that the filter hides: listed below, so Default stays reachable.
  const hiddenApplied = games.filter((g) => g.profile && !filter.keep(g));
  // Selection falls back to the first visible game when the current one is hidden.
  const selected = visible.some((g) => g.appid === appid) ? appid : visible[0]?.appid;

  useEffect(() => {
    // A backend that failed to start never answers, so don't wait forever.
    const timer = setTimeout(() => setLoadError("The Loadout backend did not respond."), 10000);
    api.getBootstrap().then(
      (b) => { clearTimeout(timer); setBoot(b); setSettings(b.settings); },
      (e) => { clearTimeout(timer); setLoadError(String(e)); },
    );
    api.listGames().then((g) => {
      setGames(g);
      // Keep the user's pick across remounts; else prefer the running game (if the filter shows it,
      // otherwise `selected` falls back to the first visible game).
      const picked = kept.get("appid");
      if (g.some((x) => x.appid === picked)) return;
      const running = window.SteamUIStore?.MainRunningAppID;
      if (g.some((x) => x.appid === running)) setAppid(running);
    }, errorToast);
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
                errorToast(result.warnings.join(" "));
                return;
              }
              api.setLaunchOptions(selected, result.launch_options);
              setSettings((await api.getBootstrap()).settings);
              setGames(await api.listGames());  // refresh the applied profile shown next to each game
              toaster.toast({ title: "Loadout", body: "Applies the next time the game launches" });
            } catch (e) {
              errorToast(e);
            }
          }}
        />,
      );
    } catch (e) {
      errorToast(e);
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
            onChange={(o) => api.setGameFilter(o.data).then(setSettings, errorToast)} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem layout="below" label="Game" disabled={!visible.length}
            strDefaultLabel="No games for this filter"
            rgOptions={visible.map((g) => ({ data: g.appid, label: gameLabel(g) }))}
            selectedOption={selected} onChange={(o) => setAppid(o.data)} />
        </PanelSectionRow>
        {hiddenApplied.length > 0 && (
          <PanelSectionRow>
            <div style={{ fontSize: 12, color: "#e8a33d" }}>
              Profiles applied to hidden games:{" "}
              {hiddenApplied.map((g) => `${g.name} (${profileLabel(g.profile)})`).join(", ")}.
              Show "All games" to change them.
            </div>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <DropdownItem layout="below" label="Profile" disabled={selected === undefined || busy}
            rgOptions={api.PROFILES.map((p) => ({ data: p.id, label: p.label }))}
            selectedOption={current} onChange={(o) => pick(o.data)} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem layout="below" label="Resolution for this game" disabled={selected === undefined}
            rgOptions={[{ data: null, label: `Global (${settings.render_resolution})` },
              ...boot.resolutions.map((r) => ({ data: r, label: r }))]}
            selectedOption={game?.resolution ?? null}
            onChange={(o) => selected !== undefined && api.setGameResolution(selected, o.data).then(setSettings, errorToast)} />
        </PanelSectionRow>
      </PanelSection>
      <PanelSection title="Settings">
        <PanelSectionRow>
          <DropdownItem layout="below" label="Device" rgOptions={boot.devices.map((d) => ({ data: d.id, label: d.name }))}
            selectedOption={settings.device}
            onChange={(o) => api.saveSettings(o.data, settings.render_resolution ?? "1080p").then(setSettings, errorToast)} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem layout="below" label="Render resolution" rgOptions={boot.resolutions.map((r) => ({ data: r, label: r }))}
            selectedOption={settings.render_resolution}
            onChange={(o) => api.saveSettings(settings.device!, o.data).then(setSettings, errorToast)} />
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
