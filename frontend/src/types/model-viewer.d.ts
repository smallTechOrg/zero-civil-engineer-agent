import type { DetailedHTMLProps, HTMLAttributes } from 'react'

/**
 * JSX intrinsic typing for the <model-viewer> custom element
 * (@google/model-viewer, registered client-side via dynamic import).
 * React 19 moved the JSX namespace under React — augment it there.
 */
type ModelViewerAttributes = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
  src?: string
  alt?: string
  poster?: string
  exposure?: number | string
  'camera-controls'?: boolean | ''
  'camera-orbit'?: string
  'shadow-intensity'?: number | string
  'field-of-view'?: string
  'interaction-prompt'?: string
  'touch-action'?: string
}

declare global {
  namespace React {
    namespace JSX {
      interface IntrinsicElements {
        'model-viewer': ModelViewerAttributes
      }
    }
  }
}

export {}
