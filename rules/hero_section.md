Act as a Senior UI/UX Engineer. Create a responsive Hero Section and Navigation Bar using React and Tailwind CSS.

**Context & Assets:**
- I have a background image located at `/public/hero-bg.png`.
- The image features 3D abstract security elements on the LEFT side.
- Therefore, all text content must be aligned to the RIGHT side to create visual balance.
- The aesthetic is "Dark Mode SaaS": deep blacks, grays, and a primary accent color of Orange/Red (to match the button in the reference).

**Requirements:**

1.  **Background Strategy:**
    - Use `hero-bg.png` as the background for the entire section (`bg-cover bg-center bg-no-repeat`).
    - Add a subtle dark overlay (gradient from black to transparent) if necessary to ensure text readability on the right side.

2.  **Navigation Bar (Floating/Glassmorphic):**
    - Fixed at the top or absolute positioned.
    - Background: `bg-black/10` with `backdrop-blur-md` (glass effect).
    - Layout: Flex row.
    - Left: Logo "Nickel" (Simple white text or placeholder icon).
    - Center: Links (Products, Company, Pricing, For Accountants).
    - Right: "Log in" (text) and "Get Started" (button, dark grey).

3.  **Hero Content (Right-Aligned):**
    - Container: Use a max-width container.
    - Grid/Flex: Align the text content block to the right half of the screen (col-span-6 offset-6 on desktop).
    - Typography styling:
        - **H1:** Text-5xl or 6xl, font-bold, tracking-tight, text-white.
        - **Sub-headline:** Text-xl, text-gray-300, font-medium.
        - **Description:** Text-lg, text-gray-400, max-width-lg.
    - **Buttons:**
        - Primary: Bright Orange (`bg-orange-600` hover `bg-orange-500`), rounded-lg, font-semibold.
        - Secondary: Dark Gray/Ghost (`bg-white/10` hover `bg-white/20`), rounded-lg.

**The Content to Insert:**

- **H1:** Secure Every Frame. Protect Every Sound.
- **Sub-headline:** End-to-end encrypted video and audio protection for creators, businesses, and teams. Your media stays private — always.
- **Description:** Encrypt videos and audio files in real time, control access, prevent leaks, and ensure complete privacy across devices and platforms.
- **Button 1:** Get Started
- **Button 2:** See How It Works

Generate the full component code now.