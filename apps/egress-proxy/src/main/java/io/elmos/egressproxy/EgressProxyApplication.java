package io.elmos.egressproxy;

import io.elmos.network.NetworkDecisionService;
import io.elmos.network.NetworkPolicy;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicLong;

public final class EgressProxyApplication {
    private EgressProxyApplication() {}
    public static void main(String[] args) throws Exception {
        int port = integer("ELMOS_PROXY_PORT", 8080, 1024, 65535);
        long maxBytes = integer("ELMOS_PROXY_MAX_TUNNEL_MB", 1024, 1, 10240) * 1024L * 1024L;
        int idleSeconds = integer("ELMOS_PROXY_IDLE_SECONDS", 120, 5, 3600);
        String workspace = require("ELMOS_WORKSPACE_ID");
        Set<String> hosts = new TreeSet<>(); for (String host : require("ELMOS_EGRESS_ALLOWED_HOSTS").split(",")) if (!host.isBlank()) hosts.add(host.trim());
        NetworkPolicy policy = new NetworkPolicy(require("ELMOS_NETWORK_POLICY_ID"), integer("ELMOS_NETWORK_POLICY_VERSION", 1, 1, Integer.MAX_VALUE), NetworkPolicy.DefaultAction.DENY, hosts, null);
        new ConnectProxy(port, workspace, policy, new NetworkDecisionService(Clock.systemUTC()), maxBytes, idleSeconds).run();
    }
    static final class ConnectProxy {
        private final int port; private final String workspace; private final NetworkPolicy policy; private final NetworkDecisionService decisions;
        private final long maxBytes; private final int idleSeconds;
        ConnectProxy(int port, String workspace, NetworkPolicy policy, NetworkDecisionService decisions, long maxBytes, int idleSeconds) {
            this.port=port; this.workspace=workspace; this.policy=policy; this.decisions=decisions; this.maxBytes=maxBytes; this.idleSeconds=idleSeconds;
        }
        void run() throws IOException {
            try (ServerSocket server = new ServerSocket()) {
                server.setReuseAddress(false); server.bind(new InetSocketAddress("0.0.0.0",port),128);
                while (!Thread.currentThread().isInterrupted()) { Socket client=server.accept(); Thread.startVirtualThread(() -> handle(client)); }
            }
        }
        void handle(Socket client) {
            String host="unknown", result="DENY", reason="invalid request"; List<String> resolved=List.of(); AtomicLong sent=new AtomicLong(), received=new AtomicLong();
            try (client) {
                client.setSoTimeout(idleSeconds*1000); ConnectRequest request=ConnectRequest.read(client.getInputStream()); host=request.host();
                InetAddress[] addresses=InetAddress.getAllByName(host); resolved=Arrays.stream(addresses).map(InetAddress::getHostAddress).sorted().toList(); var decision=decisions.decide(policy,URI.create("https://"+host),addresses);
                if (!decision.allowed()) { reason=decision.reason(); respond(client,403,"Forbidden"); return; }
                Socket upstream=new Socket(); upstream.connect(new InetSocketAddress(addresses[0],443),10_000); upstream.setSoTimeout(idleSeconds*1000);
                try (upstream) {
                    respond(client,200,"Connection Established"); result="ALLOW"; reason=decision.reason();
                    CompletableFuture<Void> outbound=CompletableFuture.runAsync(() -> copy(client,upstream,sent,maxBytes));
                    CompletableFuture<Void> inbound=CompletableFuture.runAsync(() -> copy(upstream,client,received,maxBytes));
                    outbound.whenComplete((ignored,error)->close(upstream)); inbound.whenComplete((ignored,error)->close(client));
                    CompletableFuture.allOf(outbound,inbound).join();
                }
            } catch (Exception error) { reason=error instanceof ProxyRejectedException ? error.getMessage() : "tunnel failed"; }
            finally { audit(workspace,policy,host,resolved,result,reason,sent.get(),received.get()); }
        }
    }
    record ConnectRequest(String host) {
        static ConnectRequest read(InputStream input) throws IOException {
            ByteArrayOutputStream bytes=new ByteArrayOutputStream(); int previous=-1,current;
            while ((current=input.read())>=0) { if (bytes.size()>=16*1024) throw new ProxyRejectedException("request headers exceed limit"); bytes.write(current); String value=bytes.toString(StandardCharsets.US_ASCII); if (value.endsWith("\r\n\r\n")) break; previous=current; }
            if (current<0) throw new ProxyRejectedException("incomplete proxy request");
            String[] lines=bytes.toString(StandardCharsets.US_ASCII).split("\\r\\n"); String[] request=lines[0].split(" ");
            if (request.length!=3 || !request[0].equals("CONNECT") || !request[2].startsWith("HTTP/1.")) throw new ProxyRejectedException("only HTTP CONNECT is supported");
            int separator=request[1].lastIndexOf(':'); if (separator<1 || !request[1].substring(separator+1).equals("443")) throw new ProxyRejectedException("only destination port 443 is allowed");
            String host=request[1].substring(0,separator).toLowerCase(Locale.ROOT);
            if (!host.matches("(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")) throw new ProxyRejectedException("invalid destination host");
            if (host.matches("[0-9.]+")) throw new ProxyRejectedException("IP literals are not allowed");
            return new ConnectRequest(host);
        }
    }
    private static void copy(Socket from,Socket to,AtomicLong counter,long limit) { try { byte[] buffer=new byte[32*1024]; int read; while((read=from.getInputStream().read(buffer))>=0){ if(counter.addAndGet(read)>limit) throw new ProxyRejectedException("tunnel byte limit exceeded"); to.getOutputStream().write(buffer,0,read); to.getOutputStream().flush(); } } catch(IOException error){ if(!from.isClosed()&&!to.isClosed()) throw new UncheckedIOException(error); } }
    private static void respond(Socket socket,int status,String text) throws IOException { socket.getOutputStream().write(("HTTP/1.1 "+status+" "+text+"\r\nConnection: keep-alive\r\n\r\n").getBytes(StandardCharsets.US_ASCII)); socket.getOutputStream().flush(); }
    private static void close(Socket socket){try{socket.close();}catch(IOException ignored){}}
    private static void audit(String workspace,NetworkPolicy policy,String host,List<String> addresses,String result,String reason,long sent,long received){String resolved=addresses.stream().map(value->"\""+safe(value)+"\"").collect(java.util.stream.Collectors.joining(","));System.out.printf(Locale.ROOT,"{\"workspaceId\":\"%s\",\"policyId\":\"%s\",\"policyVersion\":%d,\"host\":\"%s\",\"resolvedAddresses\":[%s],\"decision\":\"%s\",\"reason\":\"%s\",\"bytesSent\":%d,\"bytesReceived\":%d}%n",safe(workspace),safe(policy.policyId()),policy.version(),safe(host),resolved,safe(result),safe(reason),sent,received);}
    private static String safe(String value){return value==null?"":value.replace("\\","_").replace("\"","_").replace("\n","_").replace("\r","_");}
    private static String require(String name){String value=System.getenv(name);if(value==null||value.isBlank())throw new IllegalArgumentException(name+" is required");return value;}
    private static int integer(String name,int fallback,int min,int max){String value=System.getenv(name);int parsed=value==null?fallback:Integer.parseInt(value);if(parsed<min||parsed>max)throw new IllegalArgumentException(name+" is outside policy");return parsed;}
    static final class ProxyRejectedException extends RuntimeException { ProxyRejectedException(String message){super(message);} }
}
