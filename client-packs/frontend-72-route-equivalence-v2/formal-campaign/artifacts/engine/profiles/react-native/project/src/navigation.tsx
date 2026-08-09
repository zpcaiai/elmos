import { NavigationContainer, type LinkingOptions } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { ELMOS_ROUTES, elmosSelectBoundedRoute } from "./elmos-bounded-navigation";

export interface GeneratedScreenParams {
  readonly id: string; readonly path: string; readonly title: string; readonly text: string;
  readonly requiresAuth: boolean; readonly deepLink: boolean;
}
export type RootStackParamList = {
  readonly "Screen1": GeneratedScreenParams;
  readonly "Screen2": GeneratedScreenParams;
  readonly "Screen3": GeneratedScreenParams;
};
function generatedScreenName(index: number): keyof RootStackParamList { return `Screen${index + 1}` as keyof RootStackParamList; }
function resolveGeneratedScreen(path: string): keyof RootStackParamList {
  const selected = elmosSelectBoundedRoute(path);
  const index = ELMOS_ROUTES.findIndex(route => route === selected);
  if (index < 0) throw new Error("selected bounded route has no generated screen");
  return generatedScreenName(index);
}
const Stack = createNativeStackNavigator<RootStackParamList>();
interface GeneratedProps { readonly route: { readonly params: GeneratedScreenParams } }
function GeneratedScreen({ route }: GeneratedProps) {
  return <ScrollView contentContainerStyle={styles.content}><View accessible accessibilityRole="summary" accessibilityLabel={`${route.params.id}|${route.params.path}|auth:${route.params.requiresAuth}|deep:${route.params.deepLink}`}>
    <Text accessibilityRole="header" style={styles.title}>{route.params.title}</Text>
    <Text style={styles.body}>{route.params.text}</Text>
    <Text accessibilityLiveRegion="polite" style={styles.status}>生成状态：等待 Android/iOS 设备验证</Text>
  </View></ScrollView>;
}
const linking: LinkingOptions<RootStackParamList> = { prefixes: ["interaction-reactnative://"], config: { screens: Object.fromEntries(ELMOS_ROUTES.map((route, index) => [generatedScreenName(index), route.path.replace(/^\//, "") || "home"])) } };
export function GeneratedNavigation({ requestedPath = "/__elmos_initial__" }: { readonly requestedPath?: string } = {}) {
  const initialScreen = resolveGeneratedScreen(requestedPath);
  return <NavigationContainer linking={linking}><Stack.Navigator initialRouteName={initialScreen}>
    {ELMOS_ROUTES.map((route, index) => <Stack.Screen key={route.id} name={generatedScreenName(index)} component={GeneratedScreen} initialParams={{ id: route.id, path: route.path, title: route.title, text: route.text, requiresAuth: route.requiresAuth, deepLink: route.deepLink }} />)}
  </Stack.Navigator></NavigationContainer>;
}
const styles = StyleSheet.create({ content: { flexGrow: 1, padding: 24, justifyContent: "center", backgroundColor: "#f5f7fb" }, title: { fontSize: 30, fontWeight: "700", color: "#172033" }, body: { marginTop: 12, fontSize: 18, color: "#334155" }, status: { marginTop: 20, color: "#6b4f00" } });
