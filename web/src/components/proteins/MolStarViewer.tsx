'use client';

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';

/**
 * Mol* (molstar) Protein Viewer
 *
 * RCSB PDB 官网同款 3D 蛋白可视化引擎,通过 ensureMolStar() 在本组件挂载时
 * 按需把 /vendor/molstar.js 以 UMD 全局加载到 window.molstar,完全绕开
 * webpack ESM 打包 (NGL 在打包环境下有大量兼容 bug)。
 *
 * API 文档: https://github.com/molstar/molstar/tree/master/src/apps/viewer
 */

declare global {
  interface Window { molstar: any }
}

/**
 * Lazily inject /vendor/molstar.{css,js} on first viewer mount instead of
 * loading them site-wide from layout.tsx (the bundle is large and only the
 * proteins page needs it). Cached promise — concurrent mounts share one load.
 */
let molstarLoadPromise: Promise<void> | null = null;
function ensureMolStar(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve();
  if ((window as any).molstar) return Promise.resolve();
  if (!molstarLoadPromise) {
    molstarLoadPromise = new Promise<void>((resolve, reject) => {
      const css = document.createElement('link');
      css.rel = 'stylesheet';
      css.href = '/vendor/molstar.css';
      document.head.appendChild(css);
      const script = document.createElement('script');
      script.src = '/vendor/molstar.js';
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        molstarLoadPromise = null; // allow retry on next mount
        reject(new Error('Failed to load /vendor/molstar.js'));
      };
      document.body.appendChild(script);
    });
  }
  return molstarLoadPromise;
}

export type MolStarViewerHandle = {
  /** 高亮指定残基 (resno),传 null 清除 */
  highlight: (resno: number | null) => void;
};

type Props = {
  pdbUrl: string;
  /** 显示用标签 (会传给 molstar 当 structure label) */
  label?: string;
  height?: number;
};

const MolStarViewer = forwardRef<MolStarViewerHandle, Props>(function MolStarViewer(
  { pdbUrl, label, height = 500 },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);
  const pluginRef = useRef<any>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [errorMsg, setErrorMsg] = useState('');
  const [hintVisible, setHintVisible] = useState(false);

  useEffect(() => {
    let disposed = false;

    async function init() {
      if (!containerRef.current) return;
      setStatus('loading');
      setErrorMsg('');

      // 1. 按需加载 /vendor/molstar.js（只在 proteins 页挂载 viewer 时才下载）
      try {
        await ensureMolStar();
      } catch (e) {
        setErrorMsg(e instanceof Error ? e.message : String(e));
        setStatus('error');
        return;
      }
      const MS = (window as any).molstar;
      if (!MS || !MS.Viewer) {
        setErrorMsg('molstar global loaded but Viewer API missing. Check /vendor/molstar.js version.');
        setStatus('error');
        return;
      }

      // 2. 检查容器尺寸 (Mol* 必须挂在有宽高的元素上)
      const rect = containerRef.current!.getBoundingClientRect();
      if (rect.width < 50 || rect.height < 50) {
        setErrorMsg(`Container too small: ${Math.round(rect.width)}x${Math.round(rect.height)}. Mol* needs at least 50px.`);
        setStatus('error');
        return;
      }

      try {
        // 3. 创建 Viewer (配置参考 molstar 官方 embedded.html 示例)
        const viewer = await MS.Viewer.create(containerRef.current, {
          layoutIsExpanded: false,        // 不展开侧边栏,纯 3D 视图
          layoutShowControls: false,
          layoutShowRemoteState: false,
          layoutShowSequence: true,       // 底部序列条
          layoutShowLog: false,
          layoutShowLeftPanel: false,     // 隐藏左侧面板
          viewportShowExpand: true,       // 右下角全屏按钮
          viewportShowSelectionMode: false,
          viewportShowAnimation: false,
          pdbProvider: 'rcsb',
          emdbProvider: 'rcsb',
        });
        if (disposed) { viewer.dispose(); return; }
        viewerRef.current = viewer;
        pluginRef.current = viewer.plugin || viewer._plugin;

        // 4. 加载 PDB —— Mol* 直接支持 URL,不需要 Blob/File 转换
        await viewer.loadStructureFromUrl(pdbUrl, 'pdb', false, {
          label: label || 'protein',
        });

        if (disposed) return;
        setStatus('ready');
        // Show the interaction hint briefly after load, then fade it out so it
        // doesn't clutter the viewport during active exploration.
        setHintVisible(true);
        const t = setTimeout(() => setHintVisible(false), 6000);
        return () => clearTimeout(t);
      } catch (err) {
        const errObj = err as any;
        setErrorMsg(
          `Load failed:\n${errObj?.message || String(err)}\n\n` +
          (errObj?.stack || '').split('\n').slice(0, 5).join('\n')
        );
        setStatus('error');
      }
    }

    init();

    return () => {
      disposed = true;
      // molstar 的 dispose 释放 WebGL 资源
      try { viewerRef.current?.dispose?.(); } catch {}
      viewerRef.current = null;
      pluginRef.current = null;
    };
  }, [pdbUrl, label]);

  // 暴露给父组件的高亮接口 (供 BindingSitesTable 调用)
  useImperativeHandle(ref, () => ({
    highlight: (resno: number | null) => {
      const plugin = pluginRef.current;
      if (!plugin) return;
      try {
        // molstar 的 selection API 跨版本不稳定,失败就静默 (UI 不会崩)
        // 主要靠用户在 3D 视图里直接点击残基查看详情
        const interactivity = plugin?.managers?.interactivity;
        if (resno === null || resno === undefined) {
          interactivity?.loci?.clearSelection?.();
        }
        // 真正按 resno 高亮需要构造 Loci 对象,复杂且跨版本不兼容,
        // 暂时只清除,后续如需精细高亮再加
      } catch (e) {
        console.warn('[MolStarViewer] highlight failed', e);
      }
    },
  }));

  return (
    <div
      style={{
        width: '100%',
        height: `${height}px`,
        position: 'relative',
        border: '1px solid #E2E8F0',
        borderRadius: '8px',
        overflow: 'hidden',
        background: 'white',
      }}
    >
      {/* Mol* 挂载点 —— molstar 会接管这个 div 的内容 */}
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%' }}
        className="msp-viewer"
      />

      {status === 'loading' && (
        <div
          style={{
            position: 'absolute', inset: 0, display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            background: 'rgba(255,255,255,0.9)', color: '#64748B',
            fontSize: 13, pointerEvents: 'none',
          }}
        >
          <span className="inline-block w-1.5 h-1.5 bg-teal-600 rounded-full animate-pulse mr-2" />
          Loading 3D structure...
        </div>
      )}
      {status === 'ready' && (
        <div
          role="status"
          aria-live="polite"
          className={`pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-slate-900/75 px-3 py-1.5 text-[11px] font-medium text-white shadow-md transition-opacity duration-300 ${
            hintVisible ? 'opacity-100' : 'opacity-0'
          }`}
        >
          <span className="hidden sm:inline">
            🖱️ Drag to rotate · Scroll to zoom · Right-click to pan
          </span>
          <span className="sm:hidden">Drag to rotate · pinch to zoom</span>
        </div>
      )}
      {status === 'error' && (
        <div
          style={{
            position: 'absolute', inset: 0, padding: 16,
            background: '#FEF2F2', color: '#B91C1C',
            fontSize: 11, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            whiteSpace: 'pre-wrap', overflow: 'auto', textAlign: 'left',
            lineHeight: 1.5,
          }}
        >
          {errorMsg || 'Unknown error'}
        </div>
      )}
    </div>
  );
});

export default MolStarViewer;
