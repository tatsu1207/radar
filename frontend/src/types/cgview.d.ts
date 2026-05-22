declare module 'cgview' {
  export class Viewer {
    constructor(container: HTMLElement | string, options?: Record<string, any>);
    io: IO;
    draw(): void;
    resize(width: number, height: number): void;
    destroy?(): void;
  }

  export class IO {
    loadJSON(json: any): void;
    toJSON(options?: Record<string, any>): any;
    downloadSVG(filename?: string): void;
    downloadImage(width?: number, height?: number, filename?: string): void;
  }
}
