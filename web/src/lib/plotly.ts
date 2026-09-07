/**
 * Singleton loader for Plotly.js — loaded once, cached, shared by every
 * chart component that needs window.Plotly.
 *
 * Extracted from the (now-removed) VisitMap so TissueBarChart and any
 * future plot components can depend on it without coupling to the map.
 */

const PLOTLY_SRC = '/vendor/plotly.min.js';

declare global {
  interface Window {
    Plotly?: {
      newPlot: (
        root: HTMLElement,
        data: object[],
        layout: object,
        config?: object,
      ) => Promise<void>;
      react: (
        root: HTMLElement,
        data: object[],
        layout: object,
        config?: object,
      ) => Promise<void>;
      purge: (root: HTMLElement) => void;
    };
  }
}

let plotlyLoadPromise: Promise<void> | null = null;

export function loadPlotly(): Promise<void> {
  if (typeof window === 'undefined') return Promise.reject(new Error('no window'));
  if (window.Plotly) return Promise.resolve();
  if (plotlyLoadPromise) return plotlyLoadPromise;

  plotlyLoadPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      'script[data-cuagent-plotly]',
    );
    if (existing) {
      if (window.Plotly) {
        resolve();
        return;
      }
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error('plotly load failed')), {
        once: true,
      });
      return;
    }

    const script = document.createElement('script');
    script.src = PLOTLY_SRC;
    script.async = true;
    script.dataset.cuagentPlotly = 'true';
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('plotly load failed'));
    document.head.appendChild(script);
  });

  return plotlyLoadPromise;
}
