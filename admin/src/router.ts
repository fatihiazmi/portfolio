import { createRouter, createWebHistory } from "vue-router";

// FastAPI returns `index.html` for every `/admin/*` path that is not a file.
export const router = createRouter({
  history: createWebHistory("/admin/"),
  routes: [
    { path: "/", name: "dashboard", component: () => import("./views/DashboardView.vue") },
    { path: "/projects", name: "projects", component: () => import("./views/ProjectsView.vue") },
    {
      path: "/projects/new",
      name: "project-new",
      component: () => import("./views/ProjectEditView.vue"),
    },
    {
      path: "/projects/:id(\\d+)",
      name: "project-edit",
      component: () => import("./views/ProjectEditView.vue"),
      props: (route) => ({ id: Number(route.params.id) }),
    },
    { path: "/images", name: "images", component: () => import("./views/ImagesView.vue") },
    { path: "/leads", name: "leads", component: () => import("./views/LeadsView.vue") },
    { path: "/:rest(.*)*", redirect: "/" },
  ],
});
