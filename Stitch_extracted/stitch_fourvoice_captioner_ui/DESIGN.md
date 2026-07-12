---
name: Kinetic Precision
colors:
  surface: '#111412'
  surface-dim: '#111412'
  surface-bright: '#373a37'
  surface-container-lowest: '#0c0f0d'
  surface-container-low: '#191c1a'
  surface-container: '#1d201e'
  surface-container-high: '#282b28'
  surface-container-highest: '#323533'
  on-surface: '#e1e3df'
  on-surface-variant: '#d6c4b0'
  inverse-surface: '#e1e3df'
  inverse-on-surface: '#2e312f'
  outline: '#9e8e7c'
  outline-variant: '#514536'
  surface-tint: '#ffb955'
  primary: '#ffc982'
  on-primary: '#452b00'
  primary-container: '#f0a93e'
  on-primary-container: '#654000'
  inverse-primary: '#835500'
  secondary: '#79daa4'
  on-secondary: '#003921'
  secondary-container: '#00784b'
  on-secondary-container: '#9bfcc4'
  tertiary: '#d6d2ca'
  on-tertiary: '#31302b'
  tertiary-container: '#bab7af'
  on-tertiary-container: '#494842'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffddb4'
  primary-fixed-dim: '#ffb955'
  on-primary-fixed: '#291800'
  on-primary-fixed-variant: '#633f00'
  secondary-fixed: '#95f6bf'
  secondary-fixed-dim: '#79daa4'
  on-secondary-fixed: '#002111'
  on-secondary-fixed-variant: '#005232'
  tertiary-fixed: '#e6e2d9'
  tertiary-fixed-dim: '#cac6be'
  on-tertiary-fixed: '#1c1c16'
  on-tertiary-fixed-variant: '#484740'
  background: '#111412'
  on-background: '#e1e3df'
  surface-variant: '#323533'
typography:
  display-lg:
    fontFamily: Bricolage Grotesque
    fontSize: 48px
    fontWeight: '800'
    lineHeight: '1.1'
    letterSpacing: -0.04em
  display-lg-mobile:
    fontFamily: Bricolage Grotesque
    fontSize: 32px
    fontWeight: '800'
    lineHeight: '1.1'
    letterSpacing: -0.04em
  headline-md:
    fontFamily: Bricolage Grotesque
    fontSize: 24px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: '0'
  body-md:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: '0'
  label-caps:
    fontFamily: IBM Plex Mono
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '1'
    letterSpacing: 0.1em
  emphasis-italic:
    fontFamily: Libre Caslon Text
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.5'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 40px
  container-max: 1440px
---

## Brand & Style

The design system is engineered for **FourVoice Captioner**, a utility-first application that balances professional-grade functionality with a premium, editor-centric aesthetic. The brand personality is precise, efficient, and technically sophisticated, targeting content creators and editors who value speed without sacrificing visual quality.

The style is a fusion of **Modern Minimalism** and **Technical Industrialism**. It utilizes deep, "inked" surfaces to reduce eye strain during long editing sessions, while leveraging high-contrast typography and "Signal" accents to draw immediate attention to critical states (like AI confidence levels or export progress). The UI should feel like a high-end hardware console—tactile, responsive, and purposefully sparse. There are no decorative elements; every line, shadow, and transition serves a functional purpose.

## Colors

This design system utilizes a high-contrast dark palette designed for clarity and focus.

*   **Base & Surface**: The foundation is `Carbon Ink` (#0F1210), providing a near-black canvas that makes content pop. Interactive surfaces and cards use `Graphite` (#1B1F1C) to create subtle depth without relying on heavy shadows.
*   **Accents**: `Signal Amber` (#F0A93E) is reserved for primary actions, critical alerts, and active "On-Air" states. `Muted Sage` (#5FBF8C) indicates high-confidence AI transcriptions and success states.
*   **Typography & Borders**: Text is rendered in `Warm Bone` (#EDE9E0) to provide a softer, more premium contrast than pure white. `Charcoal Mist` (#2E332F) is used for structural borders and dividers to maintain the minimalist, technical grid.

## Typography

The typographic hierarchy is built on three distinct pillars to differentiate between brand, content, and utility:

1.  **Display**: **Bricolage Grotesque** is used for impactful headers and large status indicators. It should always be set with tight tracking to emphasize its geometric, bold nature.
2.  **Body**: **Inter** provides maximum legibility for long-form captions and settings.
3.  **Utility**: **IBM Plex Mono** is used for all metadata, timestamps, confidence percentages, and stage labels (e.g., "UPLOADING", "PROCESSING"). It must always be uppercase with generous letter-spacing.
4.  **Emphasis**: Use a classic serif (e.g., **Libre Caslon Text**) sparingly for editorial tooltips or subtle brand moments to provide a "human" contrast to the technical monospaced fonts.

## Layout & Spacing

This design system follows a **Fixed-Fluid Hybrid** model. While the sidebar and transcription panels are fixed-width to maintain utility, the central video preview area is fluid to maximize workspace efficiency.

*   **Rhythm**: A 4px baseline grid governs all spacing.
*   **Grid**: Use a 12-column grid for desktop with 24px gutters. Elements should snap to the grid to maintain the "functional console" feel.
*   **Safe Areas**: High-density screens should maintain a 40px outer margin, while mobile views compress this to 16px.
*   **Reflow**: On tablet and mobile, the transcription list moves below the video preview, and the technical metadata labels may be hidden to prioritize the waveform view.

## Elevation & Depth

Elevation in this design system is achieved through **Tonal Layering** and **Subtle Glows** rather than traditional shadows.

*   **Surfaces**: Background is the darkest tier. Cards and panels sit one level above with a subtle 1px border of `Charcoal Mist`.
*   **Depth**: High-importance floating elements (like export modals) use a deep backdrop blur (20px) and a very faint, 10% opacity `Signal Amber` outer glow to simulate a lit hardware button.
*   **Active States**: Interactive elements do not lift; instead, they "illuminate." An active button or selected caption block should have a vibrant border color and a slight inner glow.

## Shapes

The shape language is a deliberate contrast between technical rigidity and organic softness.

*   **Containers**: Use `rounded-xl` (24px) for major containers like the video player, upload zones, and the transcription editor to make the app feel modern and approachable.
*   **Interactive Elements**: Buttons and tags are strictly **Pill-shaped** (999px). This makes them instantly recognizable as interactive targets against the rectangular grid of the editor.
*   **Inputs**: Text fields and dropdowns follow the standard `rounded-lg` (16px) to maintain a cohesive bridge between the sharp text and rounded containers.

## Components

*   **Buttons**: Primary buttons are Pill-shaped, filled with `Signal Amber` with black text. Secondary buttons are ghost-style with `Warm Bone` borders and text.
*   **Transcription Blocks**: Cards use `Graphite` backgrounds with 20px rounded corners. The active block being edited is highlighted with a 1px `Muted Sage` border and a tiny "Confidence Score" tag in the top right using `IBM Plex Mono`.
*   **Upload Zone**: A large dashed-border container (24px roundedness) with a 40px icon. On hover, the border transitions from `Charcoal Mist` to `Signal Amber` with a magnetic pull effect on the "Browse" button.
*   **Waveform Motif**: Progress bars and audio visualizations should be rendered as thin vertical bars. Use `Signal Amber` for the played portion and `Charcoal Mist` for the remaining track.
*   **Chips/Tags**: Small pill-shaped tags used for speaker identification (e.g., "Speaker 1"). Use `Graphite` backgrounds with `Warm Bone` text in mono.
*   **Inputs**: Fields are bottom-bordered or fully enclosed in a `Charcoal Mist` frame. Focus states must be indicated by a `Signal Amber` caret and border.