package io.elmos.lowering;

import io.elmos.skeleton.SkeletonModels;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.List;

import static io.elmos.lowering.LoweringModels.*;

/** Applies one reversible callable patch only inside the declaration's generated-body markers. */
public final class GeneratedRegionPatchManager {
    public Patch apply(Path repository,CallablePlan plan,Emission emission,SkeletonModels.Result skeleton) {
        try {
            Path root=repository.toRealPath(LinkOption.NOFOLLOW_LINKS),target=root.resolve(plan.targetFile()).normalize();
            if(!target.startsWith(root)||Files.isSymbolicLink(target)||!Files.isRegularFile(target,LinkOption.NOFOLLOW_LINKS))throw new SecurityException("LOWERING_PATCH_TARGET_UNSAFE:"+plan.targetFile());
            String current=Files.readString(target),begin="<generated-body id=\""+plan.targetDeclarationId()+"\">",end="</generated-body>";
            int beginAt=current.indexOf(begin),endAt=current.indexOf(end,beginAt+begin.length());if(beginAt<0||endAt<0||current.indexOf(begin,beginAt+1)>=0)throw new IllegalStateException("GENERATED_REGION_NOT_UNIQUE:"+plan.targetDeclarationId());
            int contentStart=current.indexOf('\n',beginAt+begin.length())+1,endLineStart=current.lastIndexOf('\n',endAt)+1;if(contentStart<=0||endLineStart<contentStart)throw new IllegalStateException("GENERATED_REGION_LINES_INVALID");String body=emission.body().strip()+"\n";String existing=current.substring(contentStart,endLineStart);
            String baseHash=skeleton.manifest().createdFiles().stream().filter(value->value.path().equals(plan.targetFile())).map(SkeletonModels.GeneratedFile::contentHash).findFirst().orElseThrow(()->new IllegalStateException("SKELETON_FILE_NOT_IN_MANIFEST:"+plan.targetFile()));
            String desired=current.substring(0,contentStart)+body+current.substring(endLineStart);String currentHash=LoweringIds.hashText(current),desiredHash=LoweringIds.hashText(desired);
            if(existing.equals(body)||current.equals(desired))return patch(plan,skeleton,baseHash,desiredHash,"unchanged",emission);
            if(!current.contains("MIGRATION_BODY_PENDING")||!baseHash.equals(currentHash))throw new IllegalStateException("MANUAL_OR_GENERATED_REGION_CONFLICT:"+plan.targetFile());
            Path temporary=Files.createTempFile(target.getParent(),target.getFileName().toString(),".lowering.tmp");
            try{Files.writeString(temporary,desired,StandardCharsets.UTF_8);Files.move(temporary,target,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}finally{Files.deleteIfExists(temporary);}
            return patch(plan,skeleton,baseHash,desiredHash,"applied",emission);
        }catch(IOException error){throw new IllegalStateException("LOWERING_PATCH_FAILED",error);}
    }
    private static Patch patch(CallablePlan plan,SkeletonModels.Result skeleton,String base,String result,String status,Emission emission){return new Patch(LoweringIds.id("patch",plan.targetDeclarationId(),plan.inputHash(),result),plan.targetDeclarationId(),skeleton.plan().generationId(),base,result,plan.targetFile(),emission.sourceOperationIds(),plan.operations().stream().map(OperationPlan::ruleId).toList(),plan.openObligations(),status,true);}
}
