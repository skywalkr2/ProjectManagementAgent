import "@testing-library/jest-dom/vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { useEffect, useRef, useState } from "react";
import { startCursor } from "./cursor";

function Box(props: { children: React.ReactNode; late?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => (ref.current ? startCursor(ref.current, "box-title") : undefined), []);
  return (
    <div ref={ref} tabIndex={-1} data-testid="box">
      <h2 id="box-title">Title</h2>
      {props.children}
    </div>
  );
}

test("the cursor starts in the first field", async () => {
  render(
    <Box>
      <button type="button">Help</button>
      <label>
        Name <input />
      </label>
      <label>
        Other <textarea />
      </label>
    </Box>,
  );
  await waitFor(() => expect(screen.getByLabelText("Name")).toHaveFocus());
});

test("with no field the cursor is on the heading, which can take it", async () => {
  render(
    <Box>
      <button type="button">Yes</button>
    </Box>,
  );
  const heading = screen.getByRole("heading", { name: "Title" });
  await waitFor(() => expect(heading).toHaveFocus());
  expect(heading).toHaveAttribute("tabindex", "-1");
});

test("a field that was given the cursor already keeps it", async () => {
  render(
    <Box>
      <input aria-label="First" />
      <input aria-label="Second" autoFocus />
    </Box>,
  );
  await waitFor(() => expect(screen.getByLabelText("Second")).toHaveFocus());
  await new Promise((r) => setTimeout(r, 50));
  expect(screen.getByLabelText("Second")).toHaveFocus();
});

test("hidden and disabled fields are skipped", async () => {
  render(
    <Box>
      <input aria-label="Off" disabled />
      <div hidden>
        <input aria-label="Folded" />
      </div>
      <input type="hidden" aria-label="Hidden" />
      <input aria-label="Real" />
    </Box>,
  );
  await waitFor(() => expect(screen.getByLabelText("Real")).toHaveFocus());
});

test("a field that arrives after the dialog opened takes the cursor from the heading, until the person moves it", async () => {
  function Later() {
    const [ready, setReady] = useState(false);
    useEffect(() => {
      const id = window.setTimeout(() => setReady(true), 30);
      return () => window.clearTimeout(id);
    }, []);
    return <Box>{ready ? <input aria-label="Loaded" /> : <p>Loading</p>}</Box>;
  }
  render(<Later />);
  expect(await screen.findByLabelText("Loaded")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByLabelText("Loaded")).toHaveFocus());
});

test("a person who moved the cursor to a control first is left there when a field arrives", async () => {
  function Later() {
    const [ready, setReady] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setReady(true)}>
          Show
        </button>
        <Box>
          <button type="button">Elsewhere</button>
          {ready && <input aria-label="Loaded" />}
        </Box>
      </>
    );
  }
  render(<Later />);
  const heading = screen.getByRole("heading", { name: "Title" });
  await waitFor(() => expect(heading).toHaveFocus());
  act(() => screen.getByRole("button", { name: "Elsewhere" }).focus());
  act(() => screen.getByRole("button", { name: "Show" }).click());
  await new Promise((r) => setTimeout(r, 50));
  expect(screen.getByLabelText("Loaded")).not.toHaveFocus();
});
