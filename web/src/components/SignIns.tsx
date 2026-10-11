// Sign-ins: the services an add-on signs in to, one row each with where the sign-in stands in words and one action.
// Signing in leaves the app for the service's own page in this tab; the service sends the person back afterwards
// (see lib/sign-in-return.ts). The address the service's app registration must allow is always shown, since the
// person needs it when registering the app.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { problemText } from "../lib/problem";
import { useWords } from "../lib/wording";

type SignIn = S["SignInView"];

export function SignIns() {
  const { t } = useWords();
  const signIns = useQuery({ queryKey: ["sign-ins"], queryFn: api.signIns });
  // Nothing is shown until an add-on signs in to a service; a list that didn't load says so quietly.
  if (signIns.isPending) return null;
  if (signIns.isError) return <p className="hint">{t("sign_in.load_failed")}</p>;
  if (signIns.data.length === 0) return null;
  return (
    <section className="panel-section" aria-labelledby="sign-ins-title">
      <div className="heading">
        <h3 id="sign-ins-title">{t("sign_in.title")}</h3>
      </div>
      <p className="hint">{t("sign_in.intro")}</p>
      <ul className="queue">
        {signIns.data.map((item) => (
          <SignInRow key={item.name} item={item} />
        ))}
      </ul>
    </section>
  );
}

function SignInRow(props: { item: SignIn }) {
  const { t } = useWords();
  const act = useAct();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const { item } = props;
  const base = `sign-in-${item.name.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  const signedIn = item.status === "signed_in";

  const start = async () => {
    setBusy(true);
    setProblem("");
    try {
      const started = await api.startSignIn(item.name);
      // The service's own page replaces this one; the busy state stays until it does.
      window.location.assign(started.url);
    } catch (err) {
      setProblem(problemText(err, t));
      setBusy(false);
    }
  };

  const signOut = async () => {
    setBusy(true);
    setProblem("");
    await act(
      () => api.signOut(item.name),
      () => ({ message: t("sign_in.signed_out_toast", { label: item.label }) }),
    );
    setBusy(false);
  };

  const again = item.status === "expired";
  const label = signedIn
    ? t("sign_in.sign_out")
    : busy
      ? t("sign_in.working")
      : t(again ? "sign_in.sign_in_again" : "sign_in.sign_in");
  const named = signedIn
    ? t("sign_in.sign_out_named", { label: item.label })
    : t(again ? "sign_in.sign_in_again_named" : "sign_in.sign_in_named", { label: item.label });
  const notReady = !signedIn && !item.ready;
  const describedBy = [problem && `${base}-problem`, notReady && `${base}-not-ready`].filter(Boolean).join(" ");

  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={`${base}-title`}>
      <div className="row pair">
        <div className="text">
          <strong id={`${base}-title`}>{item.label}</strong>
          <span className="sub">{t(`sign_in.status.${item.status}`)}</span>
          {notReady && (
            <p className="hint" id={`${base}-not-ready`}>
              {t("sign_in.not_ready")}
            </p>
          )}
          {problem && (
            <p className="problem-note" id={`${base}-problem`} role="alert">
              {problem}
            </p>
          )}
          <div className="field">
            <label htmlFor={`${base}-callback`}>{t("sign_in.callback")}</label>
            <input
              id={`${base}-callback`}
              type="text"
              readOnly
              value={item.callback}
              aria-describedby={`${base}-callback-hint`}
              onFocus={(e) => e.currentTarget.select()}
            />
            <p className="hint" id={`${base}-callback-hint`}>
              {t("sign_in.callback_hint")}
            </p>
          </div>
        </div>
        <div className="acts">
          <button
            type="button"
            className="btn primary"
            data-key="primary"
            disabled={busy || notReady}
            aria-label={named}
            aria-describedby={describedBy || undefined}
            onClick={() => void (signedIn ? signOut() : start())}
          >
            {label}
          </button>
        </div>
      </div>
    </li>
  );
}
