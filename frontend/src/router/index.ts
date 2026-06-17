import { START_LOCATION, createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import HomeView from "../views/HomeView.vue";

const routes: RouteRecordRaw[] = [
  { path: "/", name: "home", component: HomeView },
  {
    path: "/web",
    name: "workbench",
    component: () => import("../views/WorkbenchView.vue")
  },
  {
    path: "/history",
    name: "history",
    component: () => import("../views/HistoryView.vue")
  },
  { path: "/:pathMatch(.*)*", redirect: "/" }
];

export const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach((to, from) => {
  if (from === START_LOCATION && to.path !== "/") {
    return "/";
  }
  return true;
});
