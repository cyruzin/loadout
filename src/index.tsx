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
  const [device, setDevice] = useState(boot.detected ?? "generic");
  const native = boot.devices.find((d) => d.id === device)?.native ?? "1080p";
  const [res, setRes] = useState<string | null>(null);
  const detectedName = boot.devices.find((d) => d.id === boot.detected)?.name;
  return (
    <PanelSection title="Setup">
      <PanelSectionRow>
        <div>{detectedName ? `Detected ${detectedName}. Is that right?` : "Device not detected, pick one:"}</div>
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem label="Device" rgOptions={boot.devices.map((d) => ({ data: d.id, label: d.name }))}
          selectedOption={device} onChange={(o) => setDevice(o.data)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem label="Render resolution" rgOptions={boot.resolutions.map((r) => ({ data: r, label: r }))}
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
  const [boot, setBoot] = useState<api.Bootstrap>();
  const [settings, setSettings] = useState<api.Settings>();
  const [games, setGames] = useState<api.Game[]>([]);
  const [appid, setAppid] = useState<number>();
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string>();

  useEffect(() => {
    // A backend that failed to start never answers, so don't wait forever.
    const timer = setTimeout(() => setLoadError("The Loadout backend did not respond."), 10000);
    api.getBootstrap().then(
      (b) => { clearTimeout(timer); setBoot(b); setSettings(b.settings); },
      (e) => { clearTimeout(timer); setLoadError(String(e)); },
    );
    api.listGames().then((g) => {
      setGames(g);
      const running = window.SteamUIStore?.MainRunningAppID;
      setAppid(g.some((x) => x.appid === running) ? running : g[0]?.appid);
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

  const game = appid !== undefined ? settings.games[String(appid)] : undefined;
  const current: api.Profile = game?.profile ?? "default";

  const pick = async (profile: api.Profile) => {
    if (appid === undefined || busy) return;
    setBusy(true);
    try {
      const before = await api.getLaunchOptions(appid);
      const plan = await api.planProfile(appid, profile, before);
      // Game config files are never written while the game runs (many games rewrite them on exit).
      const running = plan.file_writes.length > 0 && window.SteamUIStore?.MainRunningAppID === appid;
      showModal(
        <ConfirmModal
          strTitle={`Apply ${api.PROFILES.find((p) => p.id === profile)?.label}?`}
          strDescription={describe(plan, running)}
          bOKDisabled={plan.blocked || running}
          onOK={async () => {
            try {
              // Re-read: the user may have edited launch options while the dialog was open.
              const result = await api.applyProfile(appid, profile, await api.getLaunchOptions(appid));
              if (!result.applied) {
                errorToast(result.warnings.join(" "));
                return;
              }
              api.setLaunchOptions(appid, result.launch_options);
              setSettings((await api.getBootstrap()).settings);
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
          <DropdownItem label="Game" disabled={!games.length} strDefaultLabel="No games found"
            rgOptions={games.map((g) => ({ data: g.appid, label: g.name }))}
            selectedOption={appid} onChange={(o) => setAppid(o.data)} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem label="Profile" disabled={appid === undefined || busy}
            rgOptions={api.PROFILES.map((p) => ({ data: p.id, label: p.label }))}
            selectedOption={current} onChange={(o) => pick(o.data)} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem label="Resolution for this game" disabled={appid === undefined}
            rgOptions={[{ data: null, label: `Global (${settings.render_resolution})` },
              ...boot.resolutions.map((r) => ({ data: r, label: r }))]}
            selectedOption={game?.resolution ?? null}
            onChange={(o) => appid !== undefined && api.setGameResolution(appid, o.data).then(setSettings, errorToast)} />
        </PanelSectionRow>
      </PanelSection>
      <PanelSection title="Settings">
        <PanelSectionRow>
          <DropdownItem label="Device" rgOptions={boot.devices.map((d) => ({ data: d.id, label: d.name }))}
            selectedOption={settings.device}
            onChange={(o) => api.saveSettings(o.data, settings.render_resolution ?? "1080p").then(setSettings, errorToast)} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem label="Render resolution" rgOptions={boot.resolutions.map((r) => ({ data: r, label: r }))}
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
