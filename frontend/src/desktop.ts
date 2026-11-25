/**
 * 只在 pywebview 窗口里有的桥，浏览器直接访问时返回 undefined。
 * 页面据此决定要不要显示右上角的窗口按钮。
 */
type Bridge = {
  drag_begin: () => Promise<boolean>
  drag_to: (x: number, y: number, bx: number, by: number) => Promise<boolean>
  minimize: () => Promise<boolean>
  hide: () => Promise<boolean>
  set_float: (on: boolean) => Promise<boolean>
}

function bridge(): Bridge | undefined {
  return (window as any).pywebview?.api
}

export const isDesktop = () => !!bridge()

/** 拖动传绝对屏幕坐标，窗口位置交给 Python 算，避免一路累加飘走 */
export const win = {
  begin: () => bridge()?.drag_begin(),
  follow: (x: number, y: number, bx: number, by: number) => bridge()?.drag_to(x, y, bx, by),
  minimize: () => bridge()?.minimize(),
  hide: () => bridge()?.hide(),
  setFloat: (on: boolean) => bridge()?.set_float(on),
}
