import Vue from "vue";
import App from "./App.vue";
import { router } from "./router";
import "./styles.css";
Vue.config.productionTip = false;
new Vue({ router, render: create => create(App) }).$mount("#app");
