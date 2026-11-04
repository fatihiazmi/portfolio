import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import { definePreset } from "@primeuix/themes";
import Aura from "@primeuix/themes/aura";
import "primeicons/primeicons.css";
import PrimeVue from "primevue/config";
import ConfirmationService from "primevue/confirmationservice";
import ToastService from "primevue/toastservice";
import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router";
import "./style.css";

// Aura in the site's blueprint colours. Primary 500 is the site's `line-strong` blue. Buttons
// use 600: white text on it is 5.9:1. Surfaces are cool greys that end in the site's ink.
const Admin = definePreset(Aura, {
  primitive: {
    blueprint: {
      50: "#eef5fc",
      100: "#d8e8f7",
      200: "#b3d1ef",
      300: "#82b3e3",
      400: "#5294d3",
      500: "#3b7bc0",
      600: "#2c64a3",
      700: "#245085",
      800: "#1f436c",
      900: "#10284a",
      950: "#0a1c30",
    },
  },
  semantic: {
    primary: Object.fromEntries(
      [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((s) => [s, `{blueprint.${s}}`]),
    ),
    colorScheme: {
      light: {
        surface: {
          0: "#ffffff",
          50: "#f6f8fb",
          100: "#eef2f7",
          200: "#dde5ef",
          300: "#c3cfdd",
          400: "#93a4b9",
          500: "#64768d",
          600: "#4b5c72",
          700: "#364559",
          800: "#243245",
          900: "#142133",
          950: "#0a1c30",
        },
        primary: {
          color: "{primary.600}",
          contrastColor: "#ffffff",
          hoverColor: "{primary.700}",
          activeColor: "{primary.800}",
        },
        highlight: {
          background: "{primary.50}",
          focusBackground: "{primary.100}",
          color: "{primary.700}",
          focusColor: "{primary.800}",
        },
      },
    },
  },
});

createApp(App)
  .use(router)
  .use(PrimeVue, { theme: { preset: Admin, options: { darkModeSelector: false } } })
  .use(ToastService)
  .use(ConfirmationService)
  .mount("#app");
